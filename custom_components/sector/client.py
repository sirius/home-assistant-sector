"""Client module for interacting with Sector Alarm API."""

from __future__ import annotations

import asyncio
import base64
import logging

import aiohttp
import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .endpoints import get_action_endpoints, get_data_endpoints

_LOGGER = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Exception raised for authentication errors."""


class SectorAlarmAPI:
    """Class to interact with the Sector Alarm API."""

    API_URL = "https://mypagesapi.sectoralarm.net"

    def __init__(self, hass: HomeAssistant, email, password, panel_id, panel_code):
        """Initialize the API client."""
        self.hass = hass
        self.email = email
        self.password = password
        self.panel_id = panel_id
        self.panel_code = panel_code
        self.access_token = None
        self.headers = {}
        self.session = None
        self.data_endpoints = get_data_endpoints(self.panel_id)
        self.action_endpoints = get_action_endpoints()

    async def login(self):
        """Authenticate with the API and obtain an access token."""
        if self.session is None:
            self.session = async_get_clientsession(self.hass)

        login_url = f"{self.API_URL}/api/Login/Login"
        payload = {
            "userId": self.email,
            "password": self.password,
        }
        try:
            async with async_timeout.timeout(10):
                async with self.session.post(login_url, json=payload) as response:
                    if response.status != 200:
                        _LOGGER.error(
                            "Login failed with status code %s", response.status
                        )
                        raise AuthenticationError("Invalid credentials")
                    data = await response.json()
                    self.access_token = data.get("AuthorizationToken")
                    if not self.access_token:
                        _LOGGER.error("Login failed: No access token received")
                        raise AuthenticationError("Invalid credentials")
                    self.headers = {
                        "Authorization": f"Bearer {self.access_token}",
                        "Accept": "application/json",
                    }

        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout occurred during login")
            raise AuthenticationError("Timeout during login") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("Client error during login: %s", str(err))
            raise AuthenticationError("Client error during login") from err

    async def get_panel_list(self):
        """Retrieve available panels from the API."""
        data = []
        panellist_url = f"{self.API_URL}/api/account/GetPanelList"
        response = await self._get(panellist_url)
        _LOGGER.error(f"panel_payload: {response}")
        if response:
            data = [item["PanelId"] for item in response if "PanelId" in item]
        else:
            _LOGGER.error("Failed to retrieve any panels")
            return []

        return data

    async def retrieve_all_data(self):
        """Retrieve all relevant data from the API."""
        data = {}

        # Iterate over data endpoints
        for key, (method, url) in self.data_endpoints.items():
            if method == "GET":
                response = await self._get(url)
            elif method == "POST":
                # For POST requests, we need to provide the panel ID in the payload
                payload = {"PanelId": self.panel_id}
                response = await self._post(url, payload)
            else:
                _LOGGER.error("Unsupported HTTP method %s for endpoint %s", method, key)
                continue

            if response:
                data[key] = response
            else:
                _LOGGER.info("No data retrieved for %s", key)

        locks_status = await self.get_lock_status()
        data["Lock Status"] = locks_status

        return data

    async def get_lock_status(self):
        """Retrieve the lock status."""
        url = f"{self.API_URL}/api/panel/GetLockStatus?panelId={self.panel_id}"
        response = await self._get(url)
        if response:
            return response
        else:
            _LOGGER.error("Failed to retrieve lock status")
            return []

    async def _get(self, url):
        """Helper method to perform GET requests with timeout."""
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        content_type = response.headers.get("Content-Type", "")
                        if "application/json" in content_type:
                            return await response.json()
                        else:
                            text = await response.text()
                            _LOGGER.error(
                                "Received non-JSON response from %s: %s", url, text
                            )
                            return None
                    else:
                        text = await response.text()
                        _LOGGER.error(
                            "GET request to %s failed with status code %s, response: %s",
                            url,
                            response.status,
                            text,
                        )
                        return None
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout occurred during GET request to %s", url)
            return None
        except aiohttp.ClientError as e:
            _LOGGER.error("Client error during GET request to %s: %s", url, str(e))
            return None

    async def _post(self, url, payload):
        """Helper method to perform POST requests with timeout."""
        try:
            async with async_timeout.timeout(10):
                async with self.session.post(
                    url, json=payload, headers=self.headers
                ) as response:
                    if response.status == 200:
                        content_type = response.headers.get("Content-Type", "")
                        if "application/json" in content_type:
                            return await response.json()
                        else:
                            text = await response.text()
                            _LOGGER.error(
                                "Received non-JSON response from %s: %s", url, text
                            )
                            return None
                    else:
                        text = await response.text()
                        _LOGGER.error(
                            "POST request to %s failed with status code %s, response: %s",
                            url,
                            response.status,
                            text,
                        )
                        return None
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout occurred during POST request to %s", url)
            return None
        except aiohttp.ClientError as err:
            _LOGGER.error("Client error during POST request to %s: %s", url, str(err))
            return None

    async def arm_system(self, mode):
        """Arm the alarm system."""
        url = self.action_endpoints["Arm"][1]
        payload = {
            "ArmCode": self.panel_code,
            "PanelId": self.panel_id,
            "ArmType": mode,  # 'total' or 'partial'
        }
        result = await self._post(url, payload)
        if result is not None:
            _LOGGER.debug("System armed successfully")
            return True
        else:
            _LOGGER.error("Failed to arm system")
            return False

    async def disarm_system(self):
        """Disarm the alarm system."""
        url = self.action_endpoints["Disarm"][1]
        payload = {
            "DisarmCode": self.panel_code,
            "PanelId": self.panel_id,
        }
        result = await self._post(url, payload)
        if result is not None:
            _LOGGER.debug("System disarmed successfully")
            return True
        else:
            _LOGGER.error("Failed to disarm system")
            return False

    async def lock_door(self, serial_no):
        """Lock a specific door."""
        url = self.action_endpoints["Lock"][1]
        payload = {
            "LockSerial": serial_no,
            "PanelCode": self.panel_code,
            "PanelId": self.panel_id,
            "SerialNo": serial_no,
        }
        result = await self._post(url, payload)
        if result is not None:
            _LOGGER.debug("Door %s locked successfully", serial_no)
            return True
        else:
            _LOGGER.error("Failed to lock door %s", serial_no)
            return False

    async def unlock_door(self, serial_no):
        """Unlock a specific door."""
        url = self.action_endpoints["Unlock"][1]
        payload = {
            "LockSerial": serial_no,
            "PanelCode": self.panel_code,
            "PanelId": self.panel_id,
            "SerialNo": serial_no,
        }
        result = await self._post(url, payload)
        if result is not None:
            _LOGGER.debug("Door %s unlocked successfully", serial_no)
            return True
        else:
            _LOGGER.error("Failed to unlock door %s", serial_no)
            return False

    async def turn_on_smartplug(self, plug_id):
        """Turn on a smart plug."""
        url = f"{self.API_URL}/api/Panel/TurnOnSmartplug"
        payload = {
            "PanelId": self.panel_id,
            "DeviceId": plug_id,
        }
        result = await self._post(url, payload)
        if result is not None:
            _LOGGER.debug("Smart plug %s turned on successfully", plug_id)
            return True
        else:
            _LOGGER.error("Failed to turn on smart plug %s", plug_id)
            return False

    async def turn_off_smartplug(self, plug_id):
        """Turn off a smart plug."""
        url = f"{self.API_URL}/api/Panel/TurnOffSmartplug"
        payload = {
            "PanelId": self.panel_id,
            "DeviceId": plug_id,
        }
        result = await self._post(url, payload)
        if result is not None:
            _LOGGER.debug("Smart plug %s turned off successfully", plug_id)
            return True
        else:
            _LOGGER.error("Failed to turn off smart plug %s", plug_id)
            return False

    async def get_camera_image(self, serial_no):
        """Retrieve the latest image from a camera."""
        url = f"{self.API_URL}/api/camera/GetCameraImage"
        payload = {
            "PanelId": self.panel_id,
            "SerialNo": serial_no,
        }
        response = await self._post(url, payload)
        if response and response.get("ImageData"):
            image_data = base64.b64decode(response["ImageData"])
            return image_data
        _LOGGER.error("Failed to retrieve image for camera %s", serial_no)
        return None

    async def logout(self):
        """Logout from the API."""
        logout_url = f"{self.API_URL}/api/Login/Logout"
        await self._post(logout_url, {})
