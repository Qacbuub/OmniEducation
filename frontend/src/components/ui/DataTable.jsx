import { LuSearch, LuChevronLeft, LuChevronRight } from "react-icons/lu";
import { Spinner, EmptyState, Alert } from "./index";

/**
 * Server-driven table: the parent owns search/filter/page state and passes the API response
 * ({ count, page, page_size, results }). Columns: { key, header, render?, className? }.
 */
export function DataTable({
  columns, data, loading, error, search, onSearch, searchPlaceholder = "Search…",
  filters, page = 1, onPage, emptyTitle = "No records found", emptyText, caption,
}) {
  const rows = data?.results || [];
  const count = data?.count || 0;
  const size = data?.page_size || 10;
  const pages = Math.max(1, Math.ceil(count / size));
  const from = count ? (page - 1) * size + 1 : 0;
  const to = Math.min(count, page * size);

  return (
    <>
      {(onSearch || filters) && (
        <div className="table-toolbar">
          {onSearch && (
            <div className="topbar__search" style={{ maxWidth: 320 }}>
              <LuSearch aria-hidden="true" />
              <label className="sr-only" htmlFor="table-search">{searchPlaceholder}</label>
              <input id="table-search" className="input" type="search" placeholder={searchPlaceholder}
                value={search} onChange={(e) => onSearch(e.target.value)} />
            </div>
          )}
          {filters}
        </div>
      )}
      {error ? (
        <div style={{ padding: 20 }}><Alert tone="error">{error.message}</Alert></div>
      ) : loading && !rows.length ? (
        <Spinner />
      ) : !rows.length ? (
        <EmptyState title={emptyTitle}>{emptyText}</EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table" aria-busy={loading ? "true" : undefined}>
            {caption && <caption className="sr-only">{caption}</caption>}
            <thead>
              <tr>{columns.map((c) => <th key={c.key} scope="col" className={c.className}>{c.header}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  {columns.map((c) => <td key={c.key} className={c.className}>{c.render ? c.render(row) : row[c.key]}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {onPage && count > 0 && (
        <div className="table-footer">
          <span>Showing {from}–{to} of {count}</span>
          <div className="pager">
            <button type="button" className="btn btn--secondary btn--sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
              <LuChevronLeft aria-hidden="true" /> Previous
            </button>
            <button type="button" className="btn btn--secondary btn--sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
              Next <LuChevronRight aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
