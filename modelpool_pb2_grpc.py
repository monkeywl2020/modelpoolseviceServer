# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc
import warnings

import modelpool_pb2 as modelpool__pb2

GRPC_GENERATED_VERSION = '1.63.0'
GRPC_VERSION = grpc.__version__
EXPECTED_ERROR_RELEASE = '1.65.0'
SCHEDULED_RELEASE_DATE = 'June 25, 2024'
_version_not_supported = False

try:
    from grpc._utilities import first_version_is_lower
    _version_not_supported = first_version_is_lower(GRPC_VERSION, GRPC_GENERATED_VERSION)
except ImportError:
    _version_not_supported = True

if _version_not_supported:
    warnings.warn(
        f'The grpc package installed is at version {GRPC_VERSION},'
        + f' but the generated code in modelpool_pb2_grpc.py depends on'
        + f' grpcio>={GRPC_GENERATED_VERSION}.'
        + f' Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}'
        + f' or downgrade your generated code using grpcio-tools<={GRPC_VERSION}.'
        + f' This warning will become an error in {EXPECTED_ERROR_RELEASE},'
        + f' scheduled for release on {SCHEDULED_RELEASE_DATE}.',
        RuntimeWarning
    )


class ModelPoolServiceStub(object):
    """定义服务
    """

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.GetModelList = channel.unary_unary(
                '/modelpool.ModelPoolService/GetModelList',
                request_serializer=modelpool__pb2.AvailableModelsRequest.SerializeToString,
                response_deserializer=modelpool__pb2.ModelListResponse.FromString,
                _registered_method=True)
        self.GetAvailableModels = channel.unary_unary(
                '/modelpool.ModelPoolService/GetAvailableModels',
                request_serializer=modelpool__pb2.AvailableModelsRequest.SerializeToString,
                response_deserializer=modelpool__pb2.ModelListResponse.FromString,
                _registered_method=True)


class ModelPoolServiceServicer(object):
    """定义服务
    """

    def GetModelList(self, request, context):
        """获取所有模型
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def GetAvailableModels(self, request, context):
        """获取可用模型
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_ModelPoolServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'GetModelList': grpc.unary_unary_rpc_method_handler(
                    servicer.GetModelList,
                    request_deserializer=modelpool__pb2.AvailableModelsRequest.FromString,
                    response_serializer=modelpool__pb2.ModelListResponse.SerializeToString,
            ),
            'GetAvailableModels': grpc.unary_unary_rpc_method_handler(
                    servicer.GetAvailableModels,
                    request_deserializer=modelpool__pb2.AvailableModelsRequest.FromString,
                    response_serializer=modelpool__pb2.ModelListResponse.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'modelpool.ModelPoolService', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))


 # This class is part of an EXPERIMENTAL API.
class ModelPoolService(object):
    """定义服务
    """

    @staticmethod
    def GetModelList(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/modelpool.ModelPoolService/GetModelList',
            modelpool__pb2.AvailableModelsRequest.SerializeToString,
            modelpool__pb2.ModelListResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def GetAvailableModels(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/modelpool.ModelPoolService/GetAvailableModels',
            modelpool__pb2.AvailableModelsRequest.SerializeToString,
            modelpool__pb2.ModelListResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)
