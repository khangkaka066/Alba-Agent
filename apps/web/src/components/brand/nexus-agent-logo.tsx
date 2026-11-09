import { NexusOctopusLogo } from "@/components/brand/nexus-octopus-logo";

type NexusLogoProps = { size?: number; className?: string; title?: string };

export function NexusLogo(props: NexusLogoProps) {
  return <NexusOctopusLogo {...props} />;
}
