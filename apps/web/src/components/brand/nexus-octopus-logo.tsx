import { useId } from "react";
import { PATH, VIEWBOX } from "@/lib/octopus-paths.mjs";

type NexusOctopusLogoProps = { size?: number; className?: string; title?: string };

/** The NexusAgent octopus-N emblem. It is drawn in `currentColor`, so it follows the text colour of its container. */
export function NexusOctopusLogo({ size = 34, className, title = "NexusAgent" }: NexusOctopusLogoProps) {
  const titleId = useId();
  return <svg xmlns="http://www.w3.org/2000/svg" viewBox={VIEWBOX} width={size} height={size} className={className} role="img" aria-labelledby={titleId} fill="currentColor">
    <title id={titleId}>{title}</title>
    <path d={PATH} fillRule="evenodd" />
  </svg>;
}
