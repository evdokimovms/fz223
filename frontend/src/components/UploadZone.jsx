import { useState, useRef } from "react";
import { uploadFile } from "../api";

export default function UploadZone({ jobs, setJobs }) {
  const [isDragActive, setIsDragActive] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const processFiles = async (filesList) => {
    setError(null);
    const files = Array.from(filesList);

    const bad = files.filter((f) => !/\.(pdf|docx?|txt)$/i.test(f.name));
    if (bad.length) {
      setError(`Неподдерживаемый формат: ${bad.map((f) => f.name).join(", ")}. Допустимы PDF, DOCX, DOC, TXT.`);
      return;
    }

    if (jobs.length + files.length > 10) {
      setError("Максимально можно загрузить до 10 файлов в очередь.");
      return;
    }

    files.forEach(async (file) => {
      // Локальный объект состояния до ответа сервера
      const tempId = Math.random().toString(36).substring(7);
      const newJobPlaceholder = {
        id: tempId,
        fileName: file.name,
        fileSize: (file.size / 1024 / 1024).toFixed(2) + " МБ",
        status: "UPLOADING",
        progress: 10,
        stage: "Загрузка файла на сервер...",
        result: null
      };

      setJobs(prev => [newJobPlaceholder, ...prev]); 

      try {
        const data = await uploadFile(file); 
        if (data && data.job_id) {
          setJobs(prev => prev.map(j => j.id === tempId ? { ...j, id: data.job_id, status: "QUEUED", progress: 25, stage: "В очереди на обработку..." } : j));
        } else {
          throw new Error();
        }
      } catch (err) {
        setJobs(prev => prev.map(j => j.id === tempId ? { ...j, status: "ERROR", stage: "Ошибка загрузки", error: err.message } : j));
      }
    });
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setIsDragActive(true);
    } else if (e.type === "dragleave") {
      setIsDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFiles(e.dataTransfer.files);
    }
  };

  return (
    <div className="w-full">
      <div
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current.click()}
        className={`w-full min-h-[220px] border-2 border-dashed rounded-2xl flex flex-col items-center justify-center p-8 text-center cursor-pointer transition-all duration-300 backdrop-blur-sm
          ${isDragActive 
            ? "border-[#00529B] bg-blue-50/50 scale-[1.01] shadow-lg shadow-blue-100" 
            : "border-slate-200 bg-white hover:border-slate-300 hover:shadow-md hover:shadow-slate-100"
          }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => { const picked = Array.from(e.target.files); e.target.value = ""; processFiles(picked); }}
        />
        
        <div className="w-14 h-14 bg-blue-50 text-[#00529B] rounded-xl flex items-center justify-center mb-4 transition-transform group-hover:scale-110">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-7 h-7">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z" />
          </svg>
        </div>

        <p className="text-slate-700 font-semibold text-base mb-1">
          Перетащите файлы технического задания сюда
        </p>
        <p className="text-slate-400 text-sm font-normal">
          или <span className="text-[#00529B] font-medium underline decoration-2 decoration-blue-200 hover:decoration-[#00529B]">выберите файлы на устройстве</span>
        </p>
        <span className="text-xs text-slate-400 mt-4 px-3 py-1 bg-slate-100 rounded-md font-mono">
          До 10 файлов одновременно (PDF, DOCX, DOC, TXT)
        </span>
      </div>

      {error && (
        <div className="mt-3 text-sm text-red-600 bg-red-50 px-4 py-2.5 rounded-xl border border-red-100 flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 flex-shrink-0">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
          </svg>
          {error}
        </div>
      )}
    </div>
  );
}
