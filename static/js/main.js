(function(){
  // Mode sombre toggle
  const toggle = document.getElementById('darkToggle');
  const root = document.documentElement;
  function apply(mode){
    if(mode==='dark'){ root.classList.add('dark'); localStorage.setItem('theme','dark'); }
    else{ root.classList.remove('dark'); localStorage.setItem('theme','light'); }
  }
  const saved = localStorage.getItem('theme');
  apply(saved || 'light');
  if(toggle){
    toggle.addEventListener('click', ()=>{
      apply(root.classList.contains('dark') ? 'light' : 'dark');
    });
  }

  // Simple confirmation admin
  const adminForm = document.getElementById('creditDebitForm');
  if(adminForm){
    adminForm.addEventListener('submit', (e)=>{
      const c = adminForm.querySelector('input[name="confirm"]');
      if(!c.checked){
        e.preventDefault();
        alert("Veuillez cocher la confirmation.");
      }
    });
  }
})();
