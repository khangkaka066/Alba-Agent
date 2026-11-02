import { StudioApp } from "@/components/studio-app";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Settings" };

export default function ProviderSettingsPage() {
  return <StudioApp initialPage="settings" />;
}
