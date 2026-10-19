import type { Verification } from "@/lib/api";
import { humanize } from "@/lib/format";

/** A research verification grade; anything but primary-text-read is flagged. */
export function VerificationTag({ grade }: { grade: Verification }) {
  const weak = grade !== "PRIMARY_TEXT_READ";
  return (
    <span className={`grade ${weak ? "grade-weak" : "grade-primary"}`} data-grade={grade}>
      {weak && "⚠ "}
      {humanize(grade)}
    </span>
  );
}
