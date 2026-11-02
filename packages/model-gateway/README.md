# Model gateway

`nexus_model_gateway` routes approved models through an optional LiteLLM adapter. Callers supply an audited price schedule, tenant and workspace IDs, a strict token ceiling, and an approved local URL allowlist. The gateway reserves platform credits atomically before a call, records measured usage, and stores provider overruns as debt so spend is never silently forgiven. Workspace provider keys are encrypted with authenticated tenant, workspace, and provider context.
