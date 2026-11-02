import { StudioApp } from "@/components/studio-app";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Teammates & Inbox" };

export default function TeammatesPage() {
  return <StudioApp initialPage="teammates" />;
}
