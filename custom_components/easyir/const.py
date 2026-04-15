"""Constants for EasyIR integration."""

DOMAIN = "easyir"
SERVICE_SEND_RAW = "send_raw"
SERVICE_SEND_COMMAND = "send_profile_command"
CONF_IEEE = "ieee"
CONF_PROFILE_PATH = "profile_path"
CONF_PROFILE_CHOICE = "profile_choice"
CONF_ENDPOINT_ID = "endpoint_id"
CONF_VISIBLE_AREA_IDS = "visible_area_ids"
DEFAULT_ENDPOINT_ID = 1
DEFAULT_SEND_DELAY_MS = 700
PLATFORMS = ["climate"]

ZHA_DOMAIN = "zha"
ZHA_SERVICE = "issue_zigbee_cluster_command"

TS1201_CLUSTER_ID = 0xE004
TS1201_ENDPOINT_ID = DEFAULT_ENDPOINT_ID
TS1201_CLUSTER_TYPE = "in"
TS1201_COMMAND_ID = 2
TS1201_COMMAND_TYPE = "server"
