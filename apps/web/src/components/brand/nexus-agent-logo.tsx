import { NexusOctopusLogo } from "@/components/brand/nexus-octopus-logo";

type NexusAgentLogoProps = { size?: number; className?: string; title?: string };

export function NexusAgentLogo(props: NexusAgentLogoProps) {
  return <NexusOctopusLogo {...props} />;
}
