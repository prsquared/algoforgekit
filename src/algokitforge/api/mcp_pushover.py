import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from mcp.server.fastmcp import FastMCP
from algokitforge.core.pushover_mgr import pushover_mgr

mcp = FastMCP("pushover_notifications")

@mcp.tool()
async def send_notification(message: str, title: str = "AlgoKitForge") -> str:
    """Send a custom push notification to the user's phone via Pushover.
    Use this to alert the user about important manual interventions or strategy changes.
    
    Args:
        message: The message to send.
        title: Optional title for the notification.
    """
    success = await pushover_mgr.send_notification(message, title)
    if success:
        return "Notification sent successfully."
    else:
        return "Failed to send notification. Check logs and credentials."

if __name__ == "__main__":
    mcp.run(transport='stdio')
