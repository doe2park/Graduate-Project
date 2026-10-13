export function createLoadGate(){let busy=false;return {get busy(){return busy;},async run(task){if(busy)return false;busy=true;try{return await task();}finally{busy=false;}}};}
