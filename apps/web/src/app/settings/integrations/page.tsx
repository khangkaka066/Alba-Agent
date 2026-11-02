import { StudioApp } from "@/components/studio-app";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Integrations" };

export default function IntegrationsRoute() {
  return <StudioApp initialPage="integrations" />;
}
