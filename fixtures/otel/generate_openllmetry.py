"""Regenerate openllmetry-langchain.json: a GENUINE OpenLLMetry trace from a
LangChain agent loop with tools, instrumented by
opentelemetry-instrumentation-langchain, exported as real OTLP/JSON. No
hand-authored spans anywhere; whatever the instrumentation emits is what
kagua's adapter has to survive.

Deps (not part of kagua): pip install langchain-core opentelemetry-sdk \
    opentelemetry-instrumentation-langchain opentelemetry-exporter-otlp-proto-http
Note: span/trace ids and timestamps change on every run; tests assert
structure, not ids.
"""
import json

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from google.protobuf.json_format import MessageToDict

resource = Resource.create({"service.name": "workorder-agents"})
provider = TracerProvider(resource=resource)
exporter = InMemorySpanExporter()
provider.add_span_processor(SimpleSpanProcessor(exporter))

from opentelemetry.instrumentation.langchain import LangchainInstrumentor

LangchainInstrumentor().instrument(tracer_provider=provider)

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool


@tool
def workorders_read(workorder_id: str) -> str:
    """Read a work order by id."""
    return json.dumps({"id": workorder_id, "issue": "HVAC failure", "site": "Site 12"})


@tool
def vendors_search(query: str) -> str:
    """Search vendors by capability."""
    return json.dumps(["acme-hvac", "coolflow-mechanical"])


@tool
def vendors_get_quote(vendor: str, workorder_id: str) -> str:
    """Request a quote from a vendor for a work order."""
    return json.dumps({"vendor": vendor, "amount_usd": 8400})


@tool
def payments_approve(vendor: str, amount_usd: int) -> str:
    """Approve a payment to a vendor."""
    return json.dumps({"status": "approved", "vendor": vendor, "amount_usd": amount_usd})


TOOLS = {t.name: t for t in [workorders_read, vendors_search, vendors_get_quote, payments_approve]}

# scripted model turns: read -> search -> quote -> approve -> final answer
responses = [
    AIMessage(content="", tool_calls=[{"name": "workorders_read", "args": {"workorder_id": "WO-442"}, "id": "c1"}]),
    AIMessage(content="", tool_calls=[{"name": "vendors_search", "args": {"query": "HVAC repair site 12"}, "id": "c2"}]),
    AIMessage(content="", tool_calls=[{"name": "vendors_get_quote", "args": {"vendor": "acme-hvac", "workorder_id": "WO-442"}, "id": "c3"}]),
    AIMessage(content="", tool_calls=[{"name": "payments_approve", "args": {"vendor": "acme-hvac", "amount_usd": 8400}, "id": "c4"}]),
    AIMessage(content="WO-442 handled: acme-hvac approved for $8,400."),
]
model = FakeMessagesListChatModel(responses=responses)

messages = [HumanMessage(content="Handle work order WO-442 end to end.")]
for _ in range(10):
    ai = model.invoke(messages)
    messages.append(ai)
    if not ai.tool_calls:
        break
    for call in ai.tool_calls:
        result = TOOLS[call["name"]].invoke(call["args"])
        messages.append(ToolMessage(content=result, tool_call_id=call["id"]))

provider.force_flush()
spans = exporter.get_finished_spans()
print(f"captured {len(spans)} spans")
for s in spans:
    print(f"  {s.name}  attrs={dict(s.attributes)}")

req = encode_spans(spans)
doc = MessageToDict(req)
import os

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openllmetry-langchain.json")
with open(out, "w") as fh:
    json.dump(doc, fh, indent=1)
print(f"wrote {out}")
