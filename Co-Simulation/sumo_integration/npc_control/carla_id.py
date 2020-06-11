"""LCM type definitions
This file automatically generated by lcm.
DO NOT MODIFY BY HAND!!!!
"""

try:
    import cStringIO.StringIO as BytesIO
except ImportError:
    from io import BytesIO
import struct

class carla_id(object):
    __slots__ = ["vehicle_id", "carla_id"]

    __typenames__ = ["string", "int32_t"]

    __dimensions__ = [None, None]

    def __init__(self):
        self.vehicle_id = ""
        self.carla_id = 0

    def encode(self):
        buf = BytesIO()
        buf.write(carla_id._get_packed_fingerprint())
        self._encode_one(buf)
        return buf.getvalue()

    def _encode_one(self, buf):
        __vehicle_id_encoded = self.vehicle_id.encode('utf-8')
        buf.write(struct.pack('>I', len(__vehicle_id_encoded)+1))
        buf.write(__vehicle_id_encoded)
        buf.write(b"\0")
        buf.write(struct.pack(">i", self.carla_id))

    def decode(data):
        if hasattr(data, 'read'):
            buf = data
        else:
            buf = BytesIO(data)
        if buf.read(8) != carla_id._get_packed_fingerprint():
            raise ValueError("Decode error")
        return carla_id._decode_one(buf)
    decode = staticmethod(decode)

    def _decode_one(buf):
        self = carla_id()
        __vehicle_id_len = struct.unpack('>I', buf.read(4))[0]
        self.vehicle_id = buf.read(__vehicle_id_len)[:-1].decode('utf-8', 'replace')
        self.carla_id = struct.unpack(">i", buf.read(4))[0]
        return self
    _decode_one = staticmethod(_decode_one)

    _hash = None
    def _get_hash_recursive(parents):
        if carla_id in parents: return 0
        tmphash = (0x118948ec3de96312) & 0xffffffffffffffff
        tmphash  = (((tmphash<<1)&0xffffffffffffffff) + (tmphash>>63)) & 0xffffffffffffffff
        return tmphash
    _get_hash_recursive = staticmethod(_get_hash_recursive)
    _packed_fingerprint = None

    def _get_packed_fingerprint():
        if carla_id._packed_fingerprint is None:
            carla_id._packed_fingerprint = struct.pack(">Q", carla_id._get_hash_recursive([]))
        return carla_id._packed_fingerprint
    _get_packed_fingerprint = staticmethod(_get_packed_fingerprint)
