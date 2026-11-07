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
  return (
    <html lang="vi" data-theme="dark">
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `try{if(window.nexusDesktop)document.documentElement.dataset.desktop=window.nexusDesktop.platform;const t=localStorage.getItem("nexus_theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t;}catch(e){}`,
          }}
        />
      </head>
      <body><LocaleProvider>{children}</LocaleProvider></body>
    </html>
  );
}
