"""Customer support tools for the LangGraph agent."""

from langchain_core.tools import tool


@tool
def lookup_order(order_id: str) -> str:
    """Look up an order by its ID. Returns order status, tracking info, and details.

    Args:
        order_id: The customer's order ID (e.g., ORD-12345)
    """
    # In production, this would query your order database
    mock_orders = {
        "ORD-12345": {
            "status": "shipped",
            "tracking": "1Z999AA10123456784",
            "carrier": "UPS",
            "estimated_delivery": "March 7, 2026",
            "items": ["Wireless Headphones x1"],
        },
        "ORD-67890": {
            "status": "processing",
            "tracking": None,
            "carrier": None,
            "estimated_delivery": "March 10, 2026",
            "items": ["USB-C Hub x1", "Laptop Stand x1"],
        },
    }

    order = mock_orders.get(order_id.upper())
    if order:
        info = f"Order {order_id}: Status={order['status']}, Items={', '.join(order['items'])}"
        if order["tracking"]:
            info += f", Tracking={order['tracking']} via {order['carrier']}"
        info += f", ETA={order['estimated_delivery']}"
        return info
    return f"Order {order_id} not found. Please verify the order ID."


@tool
def lookup_account(email: str) -> str:
    """Look up a customer account by email address.

    Args:
        email: The customer's email address
    """
    # In production, query your customer database
    mock_accounts = {
        "john@example.com": {
            "name": "John Smith",
            "plan": "Premium",
            "since": "2024-01-15",
            "open_tickets": 0,
            "last_order": "ORD-12345",
        },
        "jane@example.com": {
            "name": "Jane Doe",
            "plan": "Basic",
            "since": "2025-06-01",
            "open_tickets": 1,
            "last_order": "ORD-67890",
        },
    }

    account = mock_accounts.get(email.lower())
    if account:
        return (
            f"Account found: {account['name']}, Plan={account['plan']}, "
            f"Member since {account['since']}, Open tickets={account['open_tickets']}, "
            f"Last order={account['last_order']}"
        )
    return f"No account found for {email}. Please check the email address."


@tool
def check_knowledge_base(query: str) -> str:
    """Search the customer support knowledge base for answers to common questions.

    Args:
        query: The customer's question or issue description
    """
    # In production, this would use RAG/vector search over your docs
    faq = {
        "return": (
            "Our return policy allows returns within 30 days of purchase. "
            "Items must be in original condition. Refunds are processed within "
            "5-7 business days after we receive the return."
        ),
        "shipping": (
            "Standard shipping takes 5-7 business days. Express shipping is "
            "2-3 business days. Free shipping on orders over $50."
        ),
        "cancel": (
            "You can cancel an order within 1 hour of placing it. After that, "
            "if the order hasn't shipped yet, contact us and we'll do our best "
            "to cancel it. If it has shipped, you can return it once received."
        ),
        "password": (
            "To reset your password: Go to the login page, click 'Forgot Password', "
            "enter your email, and follow the link in the email we send you. "
            "The reset link expires after 24 hours."
        ),
        "warranty": (
            "All products come with a 1-year manufacturer warranty covering "
            "defects in materials and workmanship. Extended warranty plans "
            "are available at checkout."
        ),
    }

    query_lower = query.lower()
    for key, answer in faq.items():
        if key in query_lower:
            return answer

    return (
        "I couldn't find a specific article about that. Let me provide what I know, "
        "or I can create a support ticket for a specialist to help you."
    )


@tool
def create_ticket(
    customer_name: str, issue_summary: str, priority: str = "normal"
) -> str:
    """Create a support ticket to escalate an issue to a human agent.

    Args:
        customer_name: The customer's name
        issue_summary: Brief description of the issue
        priority: Ticket priority - low, normal, high, urgent
    """
    import uuid

    ticket_id = f"TKT-{uuid.uuid4().hex[:6].upper()}"
    return (
        f"Support ticket created: {ticket_id}. "
        f"Priority: {priority}. "
        f"A specialist will follow up within "
        f"{'1 hour' if priority in ('high', 'urgent') else '24 hours'}. "
        f"Reference this ticket number for follow-up."
    )


@tool
def end_call(summary: str) -> str:
    """End the customer support call. Use this after confirming the customer is satisfied.

    Args:
        summary: Brief summary of the call and resolution
    """
    return f"CALL_ENDED|{summary}"


# Export all tools
support_tools = [
    lookup_order,
    lookup_account,
    check_knowledge_base,
    create_ticket,
    end_call,
]
