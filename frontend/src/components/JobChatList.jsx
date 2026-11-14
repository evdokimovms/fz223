import JobStatusRow from "./JobStatusRow";

export default function JobChatList({ jobs }) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between border-b border-slate-200/60 pb-2">
        <h3 className="text-sm font-bold tracking-wider text-slate-400 uppercase">Очередь аудита</h3>
        <span className="text-xs font-mono bg-slate-200/60 text-slate-600 px-2 py-0.5 rounded-full">
          {jobs.length} / 10 файлов
        </span>
      </div>
      
      <div className="flex flex-col gap-4">
        {jobs.map((job) => (
          <JobStatusRow key={job.id} initialJob={job} />
        ))}
      </div>
    </div>
  );
}
