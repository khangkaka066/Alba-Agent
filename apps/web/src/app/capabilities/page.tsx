import { redirect } from "next/navigation";

// Channels, MCP and skills moved to Settings → Integrations.
export default function IntegrationsRedirect(): never {
  redirect("/settings/integrations");
}
