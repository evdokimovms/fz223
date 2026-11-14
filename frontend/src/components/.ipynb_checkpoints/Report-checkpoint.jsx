export default function Report({data}){


let report={}


try{

report=
JSON.parse(data.result)

}
catch(e){}



return (

<div>
<h2>
Результат проверки
</h2>
<h3>
Риски
</h3>
<p>
{report.risk}
</p>
<h3>
Проблемы
</h3>
{
report.issues?.map(
(issue,i)=>(

<div key={i}>
<hr/>


<b>
{issue.category}
</b>


<p>
Фрагмент:
{issue.fragment}
</p>


<p>
Причина:
{issue.explanation}
</p>


<p>
Основание:
{issue.law_basis?.join(",")}
</p>


<p>
Рекомендация:
{issue.recommendation}
</p>


</div>

)

)

}


</div>

)

}