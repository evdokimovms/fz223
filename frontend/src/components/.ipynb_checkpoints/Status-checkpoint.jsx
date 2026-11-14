import {
useEffect,
useState
} from "react"


import {
getStatus
} from "../api"


import Report from "./Report"



export default function Status({job}){


const [data,setData]=useState({})


useEffect(()=>{


const timer=setInterval(async()=>{


const res=
await getStatus(job)


setData(res)


},2000)



return ()=>clearInterval(timer)


},[])



return (

<div>


<h3>
ID проверки:
</h3>


<p>
{job}
</p>


<h3>
Статус:
</h3>


<p>
{data.status}
</p>


<p>
Этап:
{data.stage}
</p>



{
data.status==="DONE" &&
<Report
data={data}
/>
}


</div>

)


}