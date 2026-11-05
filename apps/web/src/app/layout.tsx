import type { Metadata } from "next";
import { LocaleProvider } from "@/components/locale-provider";
import "./globals.css";
import "./shell.css";

export const metadata: Metadata = {
  title: { default: "NexusAgent", template: "%s · NexusAgent" },
  description: "Build, run, and govern your AI workflows.",
  icons: { icon: "/icon.svg", apple: "/brand/nexusagent-app-icon.png" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="vi" data-theme="dark"><body><LocaleProvider>{children}</LocaleProvider></body></html>;
}
