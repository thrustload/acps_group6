"""约会规划师 — AIP 协议接入"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ACPs_Footprint import ACPs_Footprint
from coze_client import CozeAgent
from aip_server import create_aip_server

AGENT_NAME = "约会规划师"
AGENT_AIC = "1.2.156.3088.0001.00001.REPPEE.8FA2BW.1.13SF"
COZE_BOT_ID = "7641605520465379391"
COZE_TOKEN = "TO_BE_FILLED"
DISPLAY_URL = "http://117.74.66.90:8006/notify"

coze = CozeAgent(bot_id=COZE_BOT_ID, token=COZE_TOKEN)


def report_footprint(src_name, src_aic, dst_name, dst_aic):
    try:
        ACPs_Footprint.notify(DISPLAY_URL, src_name, src_aic, dst_name, dst_aic)
    except Exception:
        pass


server = create_aip_server(AGENT_NAME, AGENT_AIC, coze, report_footprint, port=8091)

if __name__ == "__main__":
    print(f"[{AGENT_NAME}] AIP Server http://0.0.0.0:8091")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
