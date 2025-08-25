import logging

from flask import jsonify

logger = logging.getLogger(__name__)


def get_redfish_root():
    return jsonify(
        {
            "@odata.context": "/redfish/v1/$metadata",
            "@odata.id": "/redfish/v1",
            "@odata.type": "#ServiceRoot.v1_1_0.ServiceRoot",
            "Id": "RootService",
            "Name": "Redfish Service Root",
            "Chassis": {"@odata.id": "/redfish/v1/Chassis"},
        }
    )


def get_chassis():
    return jsonify(
        {
            "@odata.id": "/redfish/v1/Chassis",
            "Members": [{"@odata.id": "/redfish/v1/Chassis/1"}],
            "Members@odata.count": 1,
        }
    )


def get_chassis_1():
    return jsonify(
        {
            "@odata.id": "/redfish/v1/Chassis/1",
            "Id": "1",
            "Name": "Chassis 1",
            "Thermal": {"@odata.id": "/redfish/v1/Chassis/1/Thermal"},
        }
    )
