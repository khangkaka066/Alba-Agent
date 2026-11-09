import type { Metadata } from "next";
import { LocaleProvider } from "@/components/locale-provider";
import { PreferencesProvider } from "@/components/settings/preferences-provider";
import { InterfaceBoundary } from "@/components/shell/interface-boundary";
import "./globals.css";
import "./shell.css";
import "./workspace-shell.css";
import "./settings-shell.css";

export const metadata: Metadata = {
  title: { default: "Alba Agent", template: "%s · Alba Agent" },
  description: "Build, run, and govern your AI workflows.",
  icons: { icon: "/icon.svg", apple: "/brand/nexusagent-app-icon.png" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="vi" data-theme="dark"><body><LocaleProvider><PreferencesProvider><InterfaceBoundary>{children}</InterfaceBoundary></PreferencesProvider></LocaleProvider></body></html>;
}
