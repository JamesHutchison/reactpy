import base64
import datetime
import hashlib
import time
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

import orjson
import pyotp


class StateRecoveryFailureError(Exception):
    """
    Raised when state recovery fails.
    """


class StateRecoveryManager:
    def __init__(
        self,
        serializable_objects: Iterable[type],
        pepper: str,
        otp_key: str | None = None,
        otp_interval: int = (4 * 60 * 60),
        max_objects: int = 256,
        max_object_length: int = 40000,
        default_serializer: Callable[[Any], bytes] | None = None,
        deserializer_map: dict[type, Callable[[Any], Any]] | None = None,
    ) -> None:
        self._pepper = pepper
        self._max_objects = max_objects
        self._max_object_length = max_object_length
        self._otp_key = base64.b32encode(
            (otp_key or self._discover_otp_key()).encode("utf-8")
        )
        self._totp = pyotp.TOTP(self._otp_key, interval=otp_interval)
        self._default_serializer = default_serializer
        self._deserializer_map = deserializer_map or {}

        self._map_objects_to_ids(
            [
                *list(serializable_objects),
                Decimal,
                datetime.datetime,
                datetime.date,
                datetime.time,
            ]
        )

    def _map_objects_to_ids(self, serializable_objects: Iterable[type]) -> dict:
        self._object_to_type_id = {}
        self._type_id_to_object = {}
        for idx, typ in enumerate(
            (None, str, int, float, bool, list, tuple, UUID, *serializable_objects)
        ):
            idx_as_bytes = str(idx).encode("utf-8")
            self._object_to_type_id[typ] = idx_as_bytes
            self._type_id_to_object[idx_as_bytes] = typ

    def _discover_otp_key(self) -> str:
        """
        Generate an OTP key by looking at the parent directory of where
        ReactPy is installed and taking down the names and creation times
        of everything in there.
        """
        hasher = hashlib.sha256()
        parent_dir_of_root = Path(__file__).parent.parent.parent
        for thing in parent_dir_of_root.iterdir():
            hasher.update((thing.name + str(thing.stat().st_ctime)).encode("utf-8"))
        return hasher.hexdigest()

    def create_serializer(
        self, salt: str, target_time: float | None = None
    ) -> "StateRecoverySerializer":
        return StateRecoverySerializer(
            otp_code=self._totp.at(target_time or time.time()),
            pepper=self._pepper,
            salt=salt,
            object_to_type_id=self._object_to_type_id,
            type_id_to_object=self._type_id_to_object,
            max_object_length=self._max_object_length,
            default_serializer=self._default_serializer,
            deserializer_map=self._deserializer_map,
        )


class StateRecoverySerializer:

    def __init__(
        self,
        otp_code: str,
        pepper: str,
        salt: str,
        object_to_type_id: dict[Any, bytes],
        type_id_to_object: dict[bytes, Any],
        max_object_length: int,
        default_serializer: Callable[[Any], bytes] | None = None,
        deserializer_map: dict[type, Callable[[Any], Any]] | None = None,
    ) -> None:
        self._otp_code = otp_code.encode("utf-8")
        self._pepper = pepper.encode("utf-8")
        self._salt = salt.encode("utf-8")
        self._object_to_type_id = object_to_type_id
        self._type_id_to_object = type_id_to_object
        self._max_object_length = max_object_length
        self._default_serializer = default_serializer
        self._deserializer_map = deserializer_map or {}

    def serialize_state_vars(
        self, state_vars: dict[str, Any]
    ) -> dict[str, tuple[str, str, str]]:
        result = {}
        for key, value in state_vars.items():
            result[key] = self._serialize(key, value)
        return result

    def _serialize(self, key: str, obj: object) -> tuple[str, str, str]:
        if obj is None:
            return "0", "", ""
        obj_type = type(obj)
        for t in obj_type.__mro__:
            type_id = self._object_to_type_id.get(t)
            if type_id:
                break
        else:
            raise ValueError(f"Object {obj} was not white-listed for serialization")
        result = self._serialize_object(obj)
        if len(result) > self._max_object_length:
            raise ValueError(
                f"Serialized object {obj} is too long (length: {len(result)})"
            )
        signature = self._sign_serialization(key, type_id, result)
        return (
            type_id.decode("utf-8"),
            base64.urlsafe_b64encode(result).decode("utf-8"),
            signature,
        )

    def deserialize_client_state(
        self, state_vars: dict[str, tuple[str, str, str]]
    ) -> None:
        return {
            key: self._deserialize(key, type_id.encode("utf-8"), data, signature)
            for key, (type_id, data, signature) in state_vars.items()
        }

    def _deserialize(
        self, key: str, type_id: bytes, data: bytes, signature: str
    ) -> Any:
        if type_id == b"0":
            return None
        try:
            typ = self._type_id_to_object[type_id]
        except KeyError as err:
            raise StateRecoveryFailureError(f"Unknown type id {type_id}") from err

        result = base64.urlsafe_b64decode(data)
        expected_signature = self._sign_serialization(key, type_id, result)
        if expected_signature != signature:
            raise StateRecoveryFailureError(f"Signature mismatch for type id {type_id}")
        return self._deserialize_object(typ, result)

    def _sign_serialization(self, key: str, type_id: bytes, data: bytes) -> str:
        hasher = hashlib.sha256()
        hasher.update(type_id)
        hasher.update(data)
        hasher.update(self._pepper)
        hasher.update(self._otp_code)
        hasher.update(self._salt)
        hasher.update(key.encode("utf-8"))
        return hasher.hexdigest()

    def _serialize_object(self, obj: Any) -> bytes:
        return orjson.dumps(obj, default=self._default_serializer)

    def _deserialize_object(self, typ: Any, data: bytes) -> Any:
        if typ is None:
            return None
        result = orjson.loads(data)
        custom_deserializer = self._deserializer_map.get(typ)
        if custom_deserializer:
            return custom_deserializer(result)
        if isinstance(result, str):
            return typ(result)
        if isinstance(result, dict):
            return typ(**result)
        return result
