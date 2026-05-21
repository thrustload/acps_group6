"""快递小助手 — AIP 协议接入"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ACPs_Footprint import ACPs_Footprint
from coze_client import CozeAgent
from aip_server import create_aip_server

AGENT_NAME = "快递小助手"
AGENT_AIC = "1.2.156.3088.0001.00001.F4IQJP.MXLG0N.1.0NW2"
COZE_BOT_ID = "7637790749019095090"
COZE_TOKEN = "pat_QFIYhVSzqaADjDxOYysNBdyhpmhzSQ8hIEWIIPQHQtjPpiYBxHkOVOptyuoi7OX"
DISPLAY_URL = "http://117.74.66.90:8006/notify"
CERT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ca")

coze = CozeAgent(bot_id=COZE_BOT_ID, token=COZE_TOKEN)


def report_footprint(src_name, src_aic, dst_name, dst_aic):
    try:
        ACPs_Footprint.notify(DISPLAY_URL, src_name, src_aic, dst_name, dst_aic)
    except Exception:
        pass


server = create_aip_server(AGENT_NAME, AGENT_AIC, coze, report_footprint,
    port=8089,
    cert_path=os.path.join(CERT_DIR, "certs", f"{AGENT_AIC}.pem"),
    key_path=os.path.join(CERT_DIR, "private", f"{AGENT_AIC}.key"),
    ca_bundle_path=os.path.join(CERT_DIR, "certs", "trust-bundle.pem"),
)

if __name__ == "__main__":
    proto = "https" if os.path.exists(os.path.join(CERT_DIR, "certs", f"{AGENT_AIC}.pem")) else "http"
    print(f"[{AGENT_NAME}] AIP Server {proto}://0.0.0.0:{8089}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
