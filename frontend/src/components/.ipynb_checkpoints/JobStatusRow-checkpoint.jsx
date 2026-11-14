import { useEffect, useState } from "react";
import { getStatus } from "../api";
import ReportView from "./ReportView";

const GATE_STYLE = {
  PASS: "bg-emerald-50 text-emerald-700",
  REVIEW: "bg-amber-50 text-amber-700",
  FAIL: "bg-red-50 text-red-700",
};

export default function JobStatusRow({ initialJob }) {
  const [job, setJob] = useState(initialJob);

  useEffect(() => {
    if (["DONE", "ERROR", "UPLOADING"].includes(job.status)) return;

    const timer = setInterval(async () => {
      try {
        const res = await getStatus(job.id);
        setJob((prev) => ({
          ...prev,
          status: res.status,
          stage: res.stage || "Обработка...",
          progress: res.status === "DONE" ? 100 : Number(res.progress) || prev.progress,
          result: res.result,
          gate: res.gate,
          error: res.error,
        }));
      } catch (err) {
        setJob((prev) => ({ ...prev, status: "ERROR", stage: "Ошибка связи с сервером", error: err.message }));
      }
    }, 2000);

    return () => clearInterval(timer);
  }, [job.id, job.status]);

  const isDone = job.status === "DONE";
  const isError = job.status === "ERROR";

  return (
    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm transition-all duration-300 hover:shadow-md overflow-hidden">
      <div className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-start gap-3 max-w-md">
          <div className={`p-2 rounded-xl flex-shrink-0 ${isDone ? "bg-emerald-50 text-emerald-600" : isError ? "bg-red-50 text-red-600" : "bg-blue-50 text-[#00529B]"}`}>
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-slate-800 break-all">{job.fileName}</h4>
            <p className="text-xs text-slate-400 font-medium mt-0.5">ID: {job.id} • {job.fileSize}</p>
          </div>
        </div>

        <div className="flex items-center gap-3 self-end sm:self-center">
          <span className="text-xs font-medium text-slate-500 bg-slate-100 px-2.5 py-1 rounded-md max-w-[240px] truncate" title={job.stage}>
            {job.stage}
          </span>
          {isDone ? (
            <span className={`text-xs font-bold px-2.5 py-1 rounded-md ${GATE_STYLE[job.gate] || "bg-emerald-50 text-emerald-600"}`}>
              {job.gate || "Готово"}
            </span>
          ) : isError ? (
            <span className="text-xs font-bold text-red-600 bg-red-50 px-2.5 py-1 rounded-md">Сбой</span>
          ) : (
            <div className="phystech-spinner"></div>
          )}
        </div>
      </div>

      {isError && job.error && (
        <div className="px-5 pb-4 text-xs text-red-600 break-words">{job.error}</div>
      )}

      {!isDone && !isError && (
        <div className="w-full bg-slate-100 h-1">
          <div className="bg-[#00529B] h-1 transition-all duration-500 ease-out" style={{ width: `${job.progress}%` }} />
        </div>
      )}

      {isDone && job.result && (
        <div className="border-t border-slate-100 bg-slate-50/50">
          <ReportView rawData={job.result} />
        </div>
      )}
    </div>
  );
}
