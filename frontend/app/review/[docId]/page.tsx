import { db } from "@/lib/db";
import DocReviewClient from "@/components/DocReviewClient";
import { notFound } from "next/navigation";

export default async function ReviewPage({
  params,
}: {
  params: Promise<{ docId: string }>;
}) {
  const { docId } = await params;
  const doc = await db.getDoc(docId);
  if (!doc) notFound();

  return <DocReviewClient initialDoc={doc} />;
}

