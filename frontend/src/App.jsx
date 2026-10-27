import { useEffect, useState } from "react";
import { getSegments, assignSegment } from "./api.js";

// Starting values for the form (a fairly regular customer).
const START_FORM = {
  recency_days: "14",
  frequency: "15",
  monetary: "13500",
  coupon_rate: "0.1",
  app_share: "0.6",
  category_variety: "5",
};

// The 6 values the user types. avg_basket is calculated (monetary / frequency), so it is not typed.
const FIELDS = [
  { name: "recency_days", label: "Days since last order", step: "1" },
  { name: "frequency", label: "Orders in the last year", step: "1" },
  { name: "monetary", label: "Total spend (₹)", step: "0.01" },
  { name: "coupon_rate", label: "Share of orders with a coupon (0–1)", step: "0.01" },
  { name: "app_share", label: "Share of orders in the app (0–1)", step: "0.01" },
  { name: "category_variety", label: "Different categories bought (1–7)", step: "1" },
];

// Friendly names for the feature medians shown on the cards and in the comparison table.
const LABELS = {
  recency_days: "Days since last order",
  frequency: "Orders / year",
  monetary: "Total spend ₹",
  avg_basket: "Avg basket ₹",
  coupon_rate: "Coupon rate",
  app_share: "App share",
  category_variety: "Categories",
};

function formatNumber(value) {
  return Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

// One card in the overview grid.
function SegmentCard({ segment, highlighted }) {
  return (
    <article className={"segment-card" + (highlighted ? " highlighted" : "")}>
      <h3>{segment.name}</h3>
      <p className="muted small">
        {segment.customers} customers ({Math.round(segment.share * 100)}%)
      </p>
      <p>{segment.description}</p>
      <p className="action"><strong>Action:</strong> {segment.suggested_action}</p>
      <dl className="medians">
        {["recency_days", "frequency", "monetary", "coupon_rate", "app_share"].map((key) => (
          <div key={key}>
            <dt>{LABELS[key]}</dt>
            <dd>{formatNumber(segment.medians[key])}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

function App() {
  const [info, setInfo] = useState(null);          // response of GET /api/segments
  const [loadingSegments, setLoadingSegments] = useState(true);
  const [form, setForm] = useState(START_FORM);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [loading, setLoading] = useState(false);

  // Load the segment overview once when the page opens.
  useEffect(() => {
    getSegments()
      .then((data) => setInfo(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoadingSegments(false));
  }, []);

  function handleChange(event) {
    const { name, value } = event.target;
    setForm({ ...form, [name]: value });
    setFieldErrors({ ...fieldErrors, [name]: undefined }); // clear the message for this field
  }

  // Simple checks in the browser; the API checks everything again.
  function checkForm() {
    const problems = {};
    for (const field of FIELDS) {
      if (form[field.name] === "") problems[field.name] = "Required";
      else if (Number.isNaN(Number(form[field.name]))) problems[field.name] = "Must be a number";
    }
    if (!problems.frequency && Number(form.frequency) <= 0) problems.frequency = "Must be at least 1";
    return problems;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setResult(null);
    setError("");
    const problems = checkForm();
    if (Object.keys(problems).length > 0) {
      setFieldErrors(problems);
      return;
    }
    // avg_basket is always total spend divided by number of orders
    const avgBasket = Math.round((Number(form.monetary) / Number(form.frequency)) * 100) / 100;
    setLoading(true);
    try {
      const data = await assignSegment({ ...form, avg_basket: avgBasket });
      setResult(data);
    } catch (err) {
      setError(err.message);
      setFieldErrors(err.fields || {});
    } finally {
      setLoading(false);
    }
  }

  const ranges = info ? info.valid_ranges : {};

  return (
    <main className="page">
      <header>
        <h1>Customer Segments</h1>
        <p className="muted">
          FreshCart customers grouped by shopping behaviour. Enter a customer's numbers to see which segment they belong to.
        </p>
      </header>

      {error && <div className="alert">{error}</div>}

      <section>
        <h2>Segments</h2>
        {loadingSegments && <p className="muted">Loading segments…</p>}
        {info && (
          <>
            <p className="muted small">
              {info.customers_clustered} customers clustered with {info.model}. Numbers on the cards are medians.
            </p>
            <div className="segment-grid">
              {info.segments.map((s) => (
                <SegmentCard key={s.id} segment={s} highlighted={result && result.segment_id === s.id} />
              ))}
            </div>
          </>
        )}
      </section>

      {info && (
        <form onSubmit={handleSubmit} className="card" noValidate>
          <h2>Assign a customer</h2>
          <div className="grid">
            {FIELDS.map((field) => {
              const [min, max] = ranges[field.name];
              return (
                <label key={field.name}>
                  {field.label}
                  <input
                    type="number"
                    name={field.name}
                    value={form[field.name]}
                    min={min}
                    max={max}
                    step={field.step}
                    onChange={handleChange}
                    className={fieldErrors[field.name] ? "invalid" : ""}
                  />
                  <span className="hint">{fieldErrors[field.name] || `Allowed: ${min} – ${max}`}</span>
                </label>
              );
            })}
          </div>
          {fieldErrors.avg_basket && <p className="field-error">Average basket: {fieldErrors.avg_basket}</p>}
          <p className="muted small">Average basket is calculated for you as total spend ÷ orders.</p>

          <button type="submit" disabled={loading}>
            {loading ? "Assigning…" : "Find segment"}
          </button>
        </form>
      )}

      {result && (
        <section className="card result">
          <p className="muted">This customer belongs to</p>
          <p className="segment-name">{result.segment_name}</p>
          {result.fit === "borderline" && (
            <p className="warning">
              Borderline: this customer is almost as close to another segment, so treat the result with care.
            </p>
          )}
          <p>{result.description}</p>
          <p className="action"><strong>Suggested action:</strong> {result.suggested_action}</p>

          <table>
            <thead>
              <tr><th>Feature</th><th>This customer</th><th>Segment median</th><th>Compared</th></tr>
            </thead>
            <tbody>
              {result.comparison.map((c) => (
                <tr key={c.feature}>
                  <td>{LABELS[c.feature]}</td>
                  <td>{formatNumber(c.value)}</td>
                  <td>{formatNumber(c.segment_median)}</td>
                  <td className={"pos-" + c.position}>{c.position}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </main>
  );
}

export default App;
