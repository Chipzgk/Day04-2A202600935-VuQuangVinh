from __future__ import annotations

import json
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from src.config import load_env_config
from src.core.llm import build_chat_model, normalize_content
from src.core.schemas import (
    AgentResult,
    CalculateTotalsInput,
    DiscountInput,
    ListProductsInput,
    ProductDetailInput,
    SaveOrderInput,
    ToolCallRecord,
)
from src.utils.data_store import OrderDataStore

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT_DIR / "data"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "artifacts" / "orders"

env_config = load_env_config()
MODEL_NAME = env_config["MODEL"]


def build_system_prompt(today: str | None = None) -> str:
    date_context = f" Hôm nay là {today}." if today else ""
    return f"""Bạn là trợ lý ảo chuyên nghiệp quản lý đơn hàng điện tử (chỉ mảng điện tử).{date_context}
Ngôn ngữ giao tiếp DUY NHẤT: Tiếng Việt ngắn gọn, súc tích.

--- QUY TẮC CỐT LÕI (GUARDRAILS) ---
1. TỪ CHỐI NGAY LẬP TỨC (KHÔNG GỌI BẤT KỲ TOOL NÀO) NẾU YÊU CẦU:
   - Tạo hóa đơn giả.
   - Bỏ qua kiểm tra kho (stock bypass).
   - Tự ý áp dụng giảm giá thủ công / giả mạo mức giảm.
   - Các hành vi bỏ qua danh mục, chính sách.
   Trả lời từ chối lịch sự và đúng chính sách.

2. KIỂM TRA THÔNG TIN (CLARIFICATION):
   TRƯỚC KHI gọi bất kỳ tool nào, nếu thiếu MỘT TRONG CÁC thông tin sau, phải HỎI LẠI VÀ DỪNG LẠI (không gọi tool):
   - Tên khách hàng (Customer Name)
   - Số điện thoại (Phone Number)
   - Email
   - Địa chỉ giao hàng (Shipping Address)
   - Tên sản phẩm và số lượng (Ít nhất 1 món)

--- QUY TRÌNH TOOL BẮT BUỘC (Khi đủ điều kiện) ---
Nếu đã có ĐỦ 5 thông tin trên, BẮT BUỘC gọi tool theo đúng thứ tự sau:
1. `list_products`: Tìm kiếm item khách yêu cầu.
2. `get_product_details`: BẮT BUỘC PHẢI GỌI ngay sau `list_products` để lấy thông tin chi tiết và định danh sản phẩm, KỂ CẢ KHI bạn nghi ngờ sản phẩm đó hết hàng hoặc thiếu hàng trong danh mục sơ bộ. Không được bỏ qua bước này.
3. `get_discount`: Lấy mã giảm giá và discount_rate.
4. `calculate_order_totals`: Tính toán tổng tiền đơn hàng.
5. `save_order`: Lưu đơn hàng cuối cùng.

--- QUY TẮC DATA ---
CHỈ SỬ DỤNG dữ liệu do tools trả về để báo giá, số lượng, ID, discount, totals, file path. TUYỆT ĐỐI KHÔNG TỰ BỊA DATA.
"""


def build_tools(store: OrderDataStore):
    @tool(args_schema=ListProductsInput)
    def list_products(
        query: str | None = None,
        category: str | None = None,
        max_unit_price: int | None = None,
        required_tags: list[str] | None = None,
        in_stock_only: bool = True,
        limit: int = 8,
    ) -> str:
        """Search the local product catalog and return the best matching items."""
        result = store.list_products(
            query=query,
            category=category,
            max_unit_price=max_unit_price,
            required_tags=required_tags,
            in_stock_only=in_stock_only,
            limit=limit
        )
        return json.dumps(result, ensure_ascii=False)

    @tool(args_schema=ProductDetailInput)
    def get_product_details(product_ids: list[str]) -> str:
        """Return exact product details for previously discovered product IDs."""
        result = store.get_product_details(product_ids=product_ids)
        return json.dumps(result, ensure_ascii=False)

    @tool(args_schema=DiscountInput)
    def get_discount(seed_hint: str, customer_tier: str = "standard") -> str:
        """Return the simulated campaign discount for the order."""
        result = store.get_discount(seed_hint=seed_hint, customer_tier=customer_tier)
        return json.dumps(result, ensure_ascii=False)

    @tool(args_schema=CalculateTotalsInput)
    def calculate_order_totals(items, detail_token: str, discount_rate: float) -> str:
        """Validate stock and calculate the discounted order total."""
        result = store.calculate_order_totals(
            items=items, 
            detail_token=detail_token, 
            discount_rate=discount_rate
        )
        return json.dumps(result, ensure_ascii=False)

    @tool(args_schema=SaveOrderInput)
    def save_order(
        customer_name: str,
        customer_phone: str,
        customer_email: str,
        shipping_address: str,
        items,
        detail_token: str,
        discount_rate: float,
        campaign_code: str,
        customer_tier: str = "standard",
        notes: str = "",
    ) -> str:
        """Persist the final order to a local JSON file."""
        result = store.save_order(
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email,
            shipping_address=shipping_address,
            items=items,
            detail_token=detail_token,
            discount_rate=discount_rate,
            campaign_code=campaign_code,
            customer_tier=customer_tier,
            notes=notes
        )
        return json.dumps(result, ensure_ascii=False)

    return [list_products, get_product_details, get_discount, calculate_order_totals, save_order]


def build_agent(
    data_dir: Path | None = None,
    output_dir: Path | None = None,
    *,
    provider: str = "google",
    model_name: str | None = None,
    today: str | None = None,
):
    store = OrderDataStore(
        data_dir=data_dir or DEFAULT_DATA_DIR, 
        output_dir=output_dir or DEFAULT_OUTPUT_DIR,
        today=today
    )
    llm = build_chat_model(provider=provider, model_name=model_name)
    tools = build_tools(store)
    system_prompt = build_system_prompt(today)
    
    agent = create_agent(model=llm, tools=tools, system_prompt=system_prompt)
    return agent


def run_agent(
    query: str,
    *,
    provider: str = "google",
    model_name: str | None = None,
    data_dir: Path | None = None,
    output_dir: Path | None = None,
    today: str | None = None,
) -> AgentResult:
    agent = build_agent(
        data_dir=data_dir,
        output_dir=output_dir,
        provider=provider,
        model_name=model_name,
        today=today
    )
    
    response = agent.invoke({"messages": [("user", query)]})
    messages = response.get("messages", [])
    
    tool_calls = extract_tool_calls(messages)
    saved_order, save_path = extract_saved_order(tool_calls)
    final_answer = extract_final_answer(messages)
    
    return AgentResult(
        query=query,
        final_answer=final_answer,
        tool_calls=tool_calls,
        saved_order=saved_order,
        saved_order_path=save_path
    )


def extract_final_answer(messages) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return ""


def extract_tool_calls(messages) -> list[ToolCallRecord]:
    records = []
    for i, msg in enumerate(messages):
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for call in msg.tool_calls:
                result = None
                for next_msg in messages[i+1:]:
                    if isinstance(next_msg, ToolMessage) and next_msg.tool_call_id == call["id"]:
                        result = next_msg.content
                        break
                
                available_fields = ToolCallRecord.__fields__ if hasattr(ToolCallRecord, "__fields__") else ToolCallRecord.model_fields
                init_args = {"name": call["name"], "arguments": call["args"]}
                
                if "output" in available_fields:
                    init_args["output"] = result
                elif "response" in available_fields:
                    init_args["response"] = result
                elif "result" in available_fields:
                    init_args["result"] = result

                records.append(ToolCallRecord(**init_args))
    return records


def extract_saved_order(tool_calls: list[ToolCallRecord]) -> tuple[dict | None, str | None]:
    for call in tool_calls:
        if call.name == "save_order":
            tool_output = getattr(call, "output", None) or getattr(call, "response", None) or getattr(call, "result", None)
            if tool_output:
                try:
                    result_data = json.loads(tool_output)
                    saved_order = result_data.get("saved_order") or result_data
                    save_path = result_data.get("save_path") or result_data.get("saved_order_path") or result_data.get("_path")
                    return saved_order, save_path
                except json.JSONDecodeError:
                    pass
    return None, None