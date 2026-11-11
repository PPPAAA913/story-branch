document.getElementById('login-form').onsubmit=async e=>{
  e.preventDefault();const button=document.getElementById('submit'),error=document.getElementById('error');button.disabled=true;error.textContent='正在登录…';
  try{
    const response=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:document.getElementById('username').value,password:document.getElementById('password').value})});
    const data=await response.json();if(!response.ok)throw new Error(data.detail||'登录失败。');
    location.replace('/');
  }catch(err){error.textContent=err.message;}finally{button.disabled=false;}
};
