const VERDICT = {
  violation: { label: "Критическое нарушение", cls: "bg-red-50 text-red-700 border-red-100" },
  risk: { label: "Повышенный риск", cls: "bg-amber-50 text-amber-700 border-amber-100" },
  check: { label: "Проверить комплектность", cls: "bg-slate-100 text-slate-600 border-slate-200" },
};
const LEVEL = {
  green: { bar: "bg-emerald-500", text: "text-emerald-700" },
  yellow: { bar: "bg-amber-500", text: "text-amber-700" },
  red: { bar: "bg-red-500", text: "text-red-700" },
};
const GATE = {
  PASS: "bg-emerald-50 text-emerald-700 border-emerald-100",
  REVIEW: "bg-amber-50 text-amber-700 border-amber-100",
  FAIL: "bg-red-50 text-red-700 border-red-100",
};
const CATEGORY = {
  brand: "Товарный знак / производитель",
  origin: "Страна происхождения",
  standards: "ТУ / стандарты",
  exclusive: "Единственный поставщик",
  participants: "Требования к участникам",
  competition: "Ограничение конкуренции",
  completeness: "Полнота комплекта документации",
};

export default function ReportView({ rawData }) {
  let report = {};
  try {
    report = typeof rawData === "string" ? JSON.parse(rawData) : rawData;
  } catch (e) {
    return <div className="p-4 text-xs text-red-500">Не удалось разобрать структуру отчета.</div>;
  }

  const findings = report.findings || [];
  const rs = report.risk_summary || {};
  const lvl = LEVEL[rs.level] || LEVEL.green;
  const counts = rs.counts || {};
  const trend = report.history_trend || [];
  const hidden = (report.hidden_low_confidence || []).length;

  return (
    <div className="p-5 text-sm text-slate-700">
      <div className="bg-white border border-slate-200 rounded-xl p-4 mb-5">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
          <h5 className="font-bold text-xs tracking-wider uppercase text-[#00529B]">
            Результаты проверки 223-ФЗ
          </h5>
          {report.gate_decision && (
            <span className={`text-xs font-extrabold px-2.5 py-0.5 rounded-md border ${GATE[report.gate_decision]}`}>
              {report.gate_decision}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 mb-2">
          <span className={`text-2xl font-extrabold ${lvl.text}`}>{rs.score ?? 0}<span className="text-sm text-slate-400">/100</span></span>
          <div className="flex-1 bg-slate-100 h-2 rounded-full overflow-hidden">
            <div className={`${lvl.bar} h-2`} style={{ width: `${rs.score ?? 0}%` }} />
          </div>
        </div>
        {report.gate_reason && <p className="text-xs text-slate-500 mb-2">{report.gate_reason}</p>}
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="bg-emerald-100 text-emerald-800 font-medium px-2 py-0.5 rounded-full">{report.ok_count || 0} без замечаний</span>
          {counts.violation > 0 && <span className="bg-red-100 text-red-800 font-medium px-2 py-0.5 rounded-full">нарушений: {counts.violation}</span>}
          {counts.risk > 0 && <span className="bg-amber-100 text-amber-800 font-medium px-2 py-0.5 rounded-full">рисков: {counts.risk}</span>}
          {counts.check > 0 && <span className="bg-slate-200 text-slate-700 font-medium px-2 py-0.5 rounded-full">проверок: {counts.check}</span>}
          {report.elapsed_sec != null && <span className="text-slate-400 px-1 py-0.5">{report.elapsed_sec} с</span>}
        </div>
      </div>

      {findings.length === 0 ? (
        <div className="bg-emerald-50/60 border border-emerald-100 rounded-xl p-4 text-emerald-800 font-medium">
          Нарушений и критических рисков в тексте ТЗ не обнаружено.
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {findings.map((f, idx) => {
            const v = VERDICT[f.verdict] || VERDICT.risk;
            return (
              <div key={idx} className="bg-white border border-slate-200 rounded-xl p-4 hover:border-slate-300 transition-colors">
                <div className="flex items-center justify-between gap-2 flex-wrap mb-2.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-[11px] uppercase tracking-wider font-extrabold px-2.5 py-0.5 rounded-md border ${v.cls}`}>
                      {f.potential_violation ? "Потенциальное нарушение" : v.label}
                    </span>
                    <span className="text-xs text-slate-500 font-medium">{CATEGORY[f.category] || f.category}</span>
                    {f.merged_count > 1 && <span className="text-[11px] text-slate-400">× {f.merged_count}</span>}
                  </div>
                  <span className="text-xs text-slate-400 font-medium">
                    {f.rule_id} • уверенность {Math.round((f.confidence || 0) * 100)}%
                  </span>
                </div>

                {f.quote && (
                  <blockquote className="mb-3 text-slate-800 bg-slate-50 border-l-4 border-slate-300 px-3 py-2 rounded-r-lg font-mono text-xs leading-relaxed break-words">
                    «{f.quote}»
                  </blockquote>
                )}

                {f.location?.label && (
                  <div className="text-xs text-slate-500 mt-1 mb-2">📍 {f.location.label}</div>
                )}
                {f.locations?.slice(1).map((l, i) =>
                  l && (
                    <div key={i} className="text-xs text-slate-500 mb-1">и: {l.label}</div>
                  )
                )}

                  

                <ul className="list-disc pl-4 space-y-1 text-slate-600 text-xs mb-3">
                  {f.why?.map((r, i) => <li key={`w${i}`}>{r}</li>)}
                  {f.extra_risk?.map((r, i) => <li key={`e${i}`} className="text-red-700">{r}</li>)}
                  {f.mitigating?.map((r, i) => <li key={`m${i}`} className="text-emerald-700">{r}</li>)}
                  {f.llm_note && <li className="text-slate-800 font-medium italic">Контекст: {f.llm_note}</li>}
                </ul>

                {f.law_basis?.length > 0 && (
                  <div className="mb-3 text-xs flex flex-col gap-1.5">
                    <span className="font-semibold text-slate-700">Правовое основание:</span>
                    {f.law_basis.map((b, i) => (
                      <details key={i} className="bg-blue-50/60 border border-blue-100 rounded-md px-2 py-1">
                        <summary className="cursor-pointer font-mono text-blue-800">
                          {b.source_type === "internal" ? "[внутр.] " : ""}{b.text}
                        </summary>
                        {b.excerpt && <p className="mt-1 text-slate-600 leading-relaxed">«{b.excerpt}»</p>}
                      </details>
                    ))}
                  </div>
                )}

                {f.history_refs?.length > 0 && (
                  <div className="mb-3 text-xs text-slate-500">
                    <span className="font-semibold text-slate-700">Похожие прошлые закупки: </span>
                    {f.history_refs.map((h, i) => (
                      <span key={i} className="mr-2">{h.label} ({Math.round(h.score * 100)}%)</span>
                    ))}
                  </div>
                )}

                {f.recommendation && (
                  <div className="pt-2.5 border-t border-slate-100 flex items-start gap-2 text-xs">
                    <span className="font-bold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded-sm flex-shrink-0">Рекомендация</span>
                    <p className="text-slate-600 italic leading-relaxed">{f.recommendation}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {trend.length > 0 && (
        <div className="mt-5">
          <h5 className="font-bold text-xs tracking-wider uppercase text-slate-400 mb-2">История закупок</h5>
          <div className="flex flex-col gap-3">
            {trend.map((t, i) => (
              <div key={i} className="bg-white border border-slate-200 rounded-xl p-3 text-xs">
                <div className="font-semibold text-slate-700 mb-1">{CATEGORY[t.category] || t.category}</div>
                <div className="text-slate-600 mb-1">Сейчас: «{t.current_quote}»</div>
                {t.past.map((p, j) => (
                  <div key={j} className="text-slate-500">Было [{p.score}] {p.label}: «{p.excerpt}»</div>
                ))}
                <div className="mt-1 text-slate-700 italic">→ {t.insight}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {hidden > 0 && (
        <p className="mt-4 text-xs text-slate-400">Скрыто замечаний с низкой уверенностью: {hidden}</p>
      )}
    </div>
  );
}
