import { useLocation } from "react-router-dom";
import { LuConstruction } from "react-icons/lu";
import { Card, EmptyState, PageHeader } from "../../components/ui";
import { titleCase } from "../../utils/format";

/** Temporary page for modules still being built. Replaced module by module. */
export default function ComingSoon() {
  const { pathname } = useLocation();
  const name = titleCase(pathname.split("/").filter(Boolean).pop() || "");
  return (
    <>
      <PageHeader title={name} />
      <Card>
        <EmptyState icon={LuConstruction} title="This module is being built">
          The {name.toLowerCase()} screen is next on the build plan.
        </EmptyState>
      </Card>
    </>
  );
}

export function NotFound() {
  return (
    <div style={{ padding: 48 }}>
      <EmptyState title="Page not found">The page you're looking for doesn't exist or you don't have access to it.</EmptyState>
    </div>
  );
}
