import { StudioApp } from "@/components/studio-app";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Intelligence & FinOps" };

export default function IntelligencePage() {
  return <StudioApp initialPage="intelligence" />;
}
