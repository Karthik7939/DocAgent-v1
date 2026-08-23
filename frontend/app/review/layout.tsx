import Link from "next/link";

import { db } from "@/lib/db";
import ReviewSidebar from "@/components/ReviewSidebar";

export const dynamic = "force-dynamic";

export default async function ReviewLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const documents = await db.listDocs();

  return (
    <div className="flex flex-col lg:flex-row gap-6 items-start">
      <aside className="lg:sticky lg:top-16 lg:self-start flex-shrink-0 transition-all duration-300">
        <ReviewSidebar documents={documents} />
      </aside>

      <section className="min-w-0 flex-1 w-full">{children}</section>
    </div>
  );
}
