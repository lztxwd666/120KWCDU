import logging

from flask import jsonify

logger = logging.getLogger(__name__)


def get_thermal():
    return jsonify(
        {
            "@odata.id": "/redfish/v1/Chassis/1/Thermal",
            "Fans": [
                {"@odata.id": f"/redfish/v1/Chassis/1/Thermal/Fans/{i}"}
                for i in range(1, 16)
            ],
            "Pump": [
                {"@odata.id": f"/redfish/v1/Chassis/1/Thermal/Pump/{i}"}
                for i in range(1, 4)
            ]
        }
    )
