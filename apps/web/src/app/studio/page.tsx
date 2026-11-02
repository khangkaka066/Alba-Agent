import { StudioApp } from "@/components/studio-app";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Workflow Studio" };

export default function StudioPage() {
  return <StudioApp initialPage="studio" />;
}
