import Link from "next/link";

export default function NotFound() {
  return (
    <section className="pt-16">
      <h1 className="text-2xl font-medium">not found</h1>
      <p className="mt-4 text-muted">
        There is no page here. <Link href="/">See all funds</Link>.
      </p>
    </section>
  );
}
