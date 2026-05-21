"""快递小助手 — AIP 协议接入"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ACPs_Footprint import ACPs_Footprint
from coze_client import CozeAgent
from aip_server import create_aip_server

AGENT_NAME = "快递小助手"
AGENT_AIC = "1.2.156.3088.0001.00001.ZDEPKT.696GQR.1.05FY"
COZE_BOT_ID = "7637790749019095090"
COZE_TOKEN = "pat_6B25NnqRVG4SwQeevPp2v46b9uQCTJfMbHctGPNaaPGmYaeKrHs6ynB68780xXOW"
DISPLAY_URL = "http://117.74.66.90:8006/notify"

coze = CozeAgent(bot_id=COZE_BOT_ID, token=COZE_TOKEN)


def report_footprint(src_name, src_aic, dst_name, dst_aic):
    try:
        ACPs_Footprint.notify(DISPLAY_URL, src_name, src_aic, dst_name, dst_aic)
    except Exception:
        pass


server = create_aip_server(AGENT_NAME, AGENT_AIC, coze, report_footprint, port=8089)

if __name__ == "__main__":
    print(f"[{AGENT_NAME}] AIP Server http://0.0.0.0:8089")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
