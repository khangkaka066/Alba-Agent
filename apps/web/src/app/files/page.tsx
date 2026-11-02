import { redirect } from "next/navigation";

// Outputs now live in the Work view and its file tree.
export default function FilesRoute(): never {
  redirect("/studio");
}
