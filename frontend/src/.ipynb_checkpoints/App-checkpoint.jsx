import { useState } from "react";
import UploadZone from "./components/UploadZone";
import JobChatList from "./components/JobChatList";

export default function App() {
  const [jobs, setJobs] = useState([]);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center py-12 px-4 selection:bg-blue-500 selection:text-white">
      <header className="text-center mb-12 max-w-2xl">
        <div className="inline-block text-xs font-bold tracking-widest text-[#00529B] uppercase bg-blue-50 px-3 py-1 rounded-full mb-3">
          Phystech AI Compliance
        </div>
        <img
            src="/mipt_rus_inv.png"
            alt="МФТИ"
            className="mx-auto h-20 mb-6"
          />
        <p className="text-lg text-slate-500 font-normal">
          Автоматизированная проверка технических заданий на соответствие требованиям Федерального закона <span className="font-semibold text-slate-700">223-ФЗ</span>.
        </p>
      </header>

      <main className="w-full max-w-3xl flex flex-col gap-8">
        <UploadZone jobs={jobs} setJobs={setJobs} />

        {jobs.length > 0 && <JobChatList jobs={jobs} />}
      </main>

      <footer className="mt-auto pt-12 text-xs text-slate-400 font-medium">
        © {new Date().getFullYear()} Московский физико-технический институт
      </footer>
    </div>
  );
}
