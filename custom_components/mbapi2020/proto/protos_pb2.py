# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: protos.proto
# Protobuf Python Version: 5.29.5
"""Generated protocol buffer code."""

from google.protobuf import (
    descriptor as _descriptor,
    descriptor_pool as _descriptor_pool,
    symbol_database as _symbol_database,
)
from google.protobuf.internal import builder as _builder

# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n\x0cprotos.proto\x12\x05proto"3\n\x10SubscribeRequest\x12\x0e\n\x06topics\x18\x01 \x03(\t\x12\x0f\n\x07replace\x18\x02 \x01(\x08"\xbe\x01\n\x11SubscribeResponse\x12\x0f\n\x07success\x18\x01 \x01(\x08\x12\x34\n\x06\x65rrors\x18\x02 \x03(\x0b\x32$.proto.SubscribeResponse.ErrorsEntry\x12\x19\n\x11subscribed_topics\x18\x03 \x03(\t\x1aG\n\x0b\x45rrorsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\'\n\x05value\x18\x02 \x01(\x0b\x32\x18.proto.SubscriptionError:\x02\x38\x01"A\n\x12UnsubscribeRequest\x12\x0e\n\x06topics\x18\x01 \x03(\t\x12\x1b\n\x13\x61nticipate_response\x18\x02 \x01(\x08"\xc4\x01\n\x13UnsubscribeResponse\x12\x0f\n\x07success\x18\x01 \x01(\x08\x12\x36\n\x06\x65rrors\x18\x02 \x03(\x0b\x32&.proto.UnsubscribeResponse.ErrorsEntry\x12\x1b\n\x13unsubscribed_topics\x18\x03 \x03(\t\x1aG\n\x0b\x45rrorsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\'\n\x05value\x18\x02 \x01(\x0b\x32\x18.proto.SubscriptionError:\x02\x38\x01"P\n\x11SubscriptionError\x12*\n\x04\x63ode\x18\x01 \x03(\x0e\x32\x1c.proto.SubscriptionErrorType\x12\x0f\n\x07message\x18\x02 \x03(\t"\x81\x02\n\x19SubscribeToAppTwinRequest\x12\x12\n\nsession_id\x18\x01 \x01(\t\x12\x0f\n\x07\x63iam_id\x18\x02 \x01(\t\x12\x15\n\rdevice_locale\x18\x03 \x01(\t\x12\x0e\n\x06\x61pp_id\x18\x04 \x01(\t\x12\x13\n\x0b\x61pp_version\x18\x05 \x01(\t\x12+\n\x07os_name\x18\x06 \x01(\x0e\x32\x1a.proto.OperatingSystemName\x12\x12\n\nos_version\x18\x07 \x01(\t\x12\x14\n\x0c\x64\x65vice_model\x18\x08 \x01(\t\x12\x17\n\x0fnetwork_carrier\x18\t \x01(\t\x12\x13\n\x0bsdk_version\x18\n \x01(\t"B\n\x1bResubscribeToAppTwinRequest\x12\x12\n\nsession_id\x18\x01 \x01(\t\x12\x0f\n\x07\x63iam_id\x18\x02 \x01(\t"\xcc\x01\n\x1cResubscribeToAppTwinResponse\x12\x45\n\x06result\x18\x01 \x01(\x0e\x32\x35.proto.ResubscribeToAppTwinResponse.ResubscribeResult"e\n\x11ResubscribeResult\x12\x11\n\rUNKNOWN_ERROR\x10\x00\x12\x0b\n\x07SUCCESS\x10\x01\x12\x15\n\x11INVALID_JWT_ERROR\x10\x02\x12\x19\n\x15TARGET_DOES_NOT_EXIST\x10\x03"_\n\x1aSubscribeToAppTwinResponse\x12\x0f\n\x07success\x18\x01 \x01(\x08\x12\x30\n\nerror_code\x18\x02 \x01(\x0e\x32\x1c.proto.SubscriptionErrorType"3\n\x1dUnsubscribeFromAppTwinRequest\x12\x12\n\nsession_id\x18\x01 \x01(\t"\xbd\x01\n\x1eUnsubscribeFromAppTwinResponse\x12\x0f\n\x07success\x18\x01 \x01(\x08\x12\x41\n\x06\x65rrors\x18\x02 \x03(\x0b\x32\x31.proto.UnsubscribeFromAppTwinResponse.ErrorsEntry\x1aG\n\x0b\x45rrorsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\'\n\x05value\x18\x02 \x01(\x0b\x32\x18.proto.SubscriptionError:\x02\x38\x01"\x0b\n\tHeartbeat" \n\x10\x41ssignedVehicles\x12\x0c\n\x04vins\x18\x01 \x03(\t"\x1d\n\x1b\x41\x63knowledgeAssignedVehicles*5\n\x15SubscriptionErrorType\x12\x0b\n\x07UNKNOWN\x10\x00\x12\x0f\n\x0bINVALID_JWT\x10\x01*q\n\x13OperatingSystemName\x12\x1c\n\x18UNKNOWN_OPERATING_SYSTEM\x10\x00\x12\x07\n\x03IOS\x10\x01\x12\x0b\n\x07\x41NDROID\x10\x02\x12\x0c\n\x08INT_TEST\x10\x03\x12\x0f\n\x0bMANUAL_TEST\x10\x04\x12\x07\n\x03WEB\x10\x05\x42\x1c\n\x1a\x63om.daimler.mbcarkit.protob\x06proto3'
)

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "protos_pb2", _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    _globals["DESCRIPTOR"]._loaded_options = None
    _globals["DESCRIPTOR"]._serialized_options = b"\n\032com.daimler.mbcarkit.proto"
    _globals["_SUBSCRIBERESPONSE_ERRORSENTRY"]._loaded_options = None
    _globals["_SUBSCRIBERESPONSE_ERRORSENTRY"]._serialized_options = b"8\001"
    _globals["_UNSUBSCRIBERESPONSE_ERRORSENTRY"]._loaded_options = None
    _globals["_UNSUBSCRIBERESPONSE_ERRORSENTRY"]._serialized_options = b"8\001"
    _globals["_UNSUBSCRIBEFROMAPPTWINRESPONSE_ERRORSENTRY"]._loaded_options = None
    _globals["_UNSUBSCRIBEFROMAPPTWINRESPONSE_ERRORSENTRY"]._serialized_options = b"8\001"
    _globals["_SUBSCRIPTIONERRORTYPE"]._serialized_start = 1572
    _globals["_SUBSCRIPTIONERRORTYPE"]._serialized_end = 1625
    _globals["_OPERATINGSYSTEMNAME"]._serialized_start = 1627
    _globals["_OPERATINGSYSTEMNAME"]._serialized_end = 1740
    _globals["_SUBSCRIBEREQUEST"]._serialized_start = 23
    _globals["_SUBSCRIBEREQUEST"]._serialized_end = 74
    _globals["_SUBSCRIBERESPONSE"]._serialized_start = 77
    _globals["_SUBSCRIBERESPONSE"]._serialized_end = 267
    _globals["_SUBSCRIBERESPONSE_ERRORSENTRY"]._serialized_start = 196
    _globals["_SUBSCRIBERESPONSE_ERRORSENTRY"]._serialized_end = 267
    _globals["_UNSUBSCRIBEREQUEST"]._serialized_start = 269
    _globals["_UNSUBSCRIBEREQUEST"]._serialized_end = 334
    _globals["_UNSUBSCRIBERESPONSE"]._serialized_start = 337
    _globals["_UNSUBSCRIBERESPONSE"]._serialized_end = 533
    _globals["_UNSUBSCRIBERESPONSE_ERRORSENTRY"]._serialized_start = 196
    _globals["_UNSUBSCRIBERESPONSE_ERRORSENTRY"]._serialized_end = 267
    _globals["_SUBSCRIPTIONERROR"]._serialized_start = 535
    _globals["_SUBSCRIPTIONERROR"]._serialized_end = 615
    _globals["_SUBSCRIBETOAPPTWINREQUEST"]._serialized_start = 618
    _globals["_SUBSCRIBETOAPPTWINREQUEST"]._serialized_end = 875
    _globals["_RESUBSCRIBETOAPPTWINREQUEST"]._serialized_start = 877
    _globals["_RESUBSCRIBETOAPPTWINREQUEST"]._serialized_end = 943
    _globals["_RESUBSCRIBETOAPPTWINRESPONSE"]._serialized_start = 946
    _globals["_RESUBSCRIBETOAPPTWINRESPONSE"]._serialized_end = 1150
    _globals["_RESUBSCRIBETOAPPTWINRESPONSE_RESUBSCRIBERESULT"]._serialized_start = 1049
    _globals["_RESUBSCRIBETOAPPTWINRESPONSE_RESUBSCRIBERESULT"]._serialized_end = 1150
    _globals["_SUBSCRIBETOAPPTWINRESPONSE"]._serialized_start = 1152
    _globals["_SUBSCRIBETOAPPTWINRESPONSE"]._serialized_end = 1247
    _globals["_UNSUBSCRIBEFROMAPPTWINREQUEST"]._serialized_start = 1249
    _globals["_UNSUBSCRIBEFROMAPPTWINREQUEST"]._serialized_end = 1300
    _globals["_UNSUBSCRIBEFROMAPPTWINRESPONSE"]._serialized_start = 1303
    _globals["_UNSUBSCRIBEFROMAPPTWINRESPONSE"]._serialized_end = 1492
    _globals["_UNSUBSCRIBEFROMAPPTWINRESPONSE_ERRORSENTRY"]._serialized_start = 196
    _globals["_UNSUBSCRIBEFROMAPPTWINRESPONSE_ERRORSENTRY"]._serialized_end = 267
    _globals["_HEARTBEAT"]._serialized_start = 1494
    _globals["_HEARTBEAT"]._serialized_end = 1505
    _globals["_ASSIGNEDVEHICLES"]._serialized_start = 1507
    _globals["_ASSIGNEDVEHICLES"]._serialized_end = 1539
    _globals["_ACKNOWLEDGEASSIGNEDVEHICLES"]._serialized_start = 1541
    _globals["_ACKNOWLEDGEASSIGNEDVEHICLES"]._serialized_end = 1570
# @@protoc_insertion_point(module_scope)
