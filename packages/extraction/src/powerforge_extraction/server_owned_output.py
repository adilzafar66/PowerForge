"""Stage 2 provider schema with server-owned assertion identifiers."""

from copy import deepcopy
from typing import Annotated

from pydantic import Field, create_model

from powerforge_extraction.stage_contracts import (
    MAX_ATTRIBUTE_ASSERTIONS,
    Contract,
    InferredAssertion,
    RawUnmappedAssertion,
    RegistryAssertion,
)

SERVER_OWNED_OUTPUT_VERSION = "server-owned-assertions-v1"
RAW_RECEIVE_LIMIT = 32


def _without_identifier(model):
    # Preserve field metadata and order. Admission runs the original model,
    # including its cross-field validators, after assigning the identifier.
    return create_model(
        f"Provider{model.__name__}",
        __base__=Contract,
        **{
            name: (field.annotation, deepcopy(field))
            for name, field in model.model_fields.items()
            if name != "local_ref"
        },
    )


ProviderRegistryAssertion = _without_identifier(RegistryAssertion)
ProviderInferredAssertion = _without_identifier(InferredAssertion)
ProviderRawUnmappedAssertion = _without_identifier(RawUnmappedAssertion)


class ServerOwnedAttributeResponse(Contract):
    attributes: Annotated[
        tuple[ProviderRegistryAssertion | ProviderInferredAssertion, ...],
        Field(max_length=MAX_ATTRIBUTE_ASSERTIONS),
    ]
    raw_unmapped: Annotated[
        tuple[ProviderRawUnmappedAssertion, ...], Field(max_length=RAW_RECEIVE_LIMIT)
    ]


def assertion_ref(collection, index):
    return f"{'attr' if collection == 'attributes' else 'raw'}-{index}"
