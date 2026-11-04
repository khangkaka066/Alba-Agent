import { StudioApp } from "@/components/studio-app";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return <StudioApp initialPage="general" />;
}
