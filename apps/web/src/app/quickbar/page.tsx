import { QuickBar } from "@/components/quickbar";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Quick task" };

export default function QuickBarPage() {
  return <QuickBar />;
}
