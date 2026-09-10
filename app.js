document.addEventListener("DOMContentLoaded",()=>{
  const views=[...document.querySelectorAll(".app-view")];
  const navBtns=[...document.querySelectorAll(".app-nav button")];
  const title=document.getElementById("view-title");
  const toast=document.getElementById("toast");
  const titles={home:"Radar",stories:"Stories",create:"Create",sources:"Sources",publish:"Publish",analytics:"Analytics"};
  let currentUrl="";
  let currentStoryTitle="Story detected from source";

  const showToast=m=>{toast.textContent=m;toast.classList.add("show");setTimeout(()=>toast.classList.remove("show"),1800)};

  function openView(name){
    views.forEach(v=>v.classList.remove("active"));
    document.getElementById("view-"+name)?.classList.add("active");
    navBtns.forEach(b=>b.classList.toggle("active",b.dataset.view===name));
    title.textContent=titles[name]||"Story Workspace";
  }

  navBtns.forEach(b=>b.addEventListener("click",()=>openView(b.dataset.view)));

  function validYouTube(v){
    try{
      const u=new URL(v);
      return ["youtube.com","www.youtube.com","youtu.be","m.youtube.com"].includes(u.hostname);
    }catch{return false}
  }

  function openWorkspace(storyTitle,sourceLabel,url=""){
    currentUrl=url;
    currentStoryTitle=storyTitle||"Story detected from source";
    views.forEach(x=>x.classList.remove("active"));
    document.getElementById("story-workspace").classList.add("active");
    title.textContent="Story Workspace";
    document.getElementById("story-title").textContent=currentStoryTitle;
    document.getElementById("story-source-label").textContent=sourceLabel||url||"Indexed source";
  }

  function analyze(v){
    if(!validYouTube(v)){showToast("Paste a valid YouTube URL.");return}
    openWorkspace("Story detected from YouTube source",v,v);
    showToast("Source indexed — demo workspace created");
  }

  document.getElementById("source-form")?.addEventListener("submit",e=>{e.preventDefault();analyze(document.getElementById("source-url").value.trim())});
  document.getElementById("source-form-alt")?.addEventListener("submit",e=>{e.preventDefault();analyze(document.getElementById("source-url-alt").value.trim())});
  document.querySelectorAll("[data-create-demo]").forEach(b=>b.addEventListener("click",()=>openWorkspace("Story opportunity from Radar","Radar-discovered source")));
  document.getElementById("back-radar")?.addEventListener("click",()=>openView("home"));
  document.getElementById("new-story-btn")?.addEventListener("click",()=>openView("create"));

  document.querySelectorAll("[data-open-story]").forEach(b=>b.addEventListener("click",()=>{
    openWorkspace(b.dataset.storyTitle,b.dataset.storySource);
    showToast("Story Workspace opened");
  }));

  document.querySelectorAll(".moment").forEach((m,i)=>m.addEventListener("click",()=>{
    document.querySelectorAll(".moment").forEach(x=>x.classList.remove("active"));
    m.classList.add("active");
    const names=["THE SOURCE REVEALS ONE IMPORTANT DETAIL","A SECOND STORY ANGLE EMERGES","ONE QUOTE COULD TRAVEL ACROSS PLATFORMS"];
    const times=["08:14–08:31","19:32–19:54","31:07–31:26"];
    document.getElementById("claim-headline").textContent=names[i];
    document.getElementById("claim-time").textContent=times[i];
  }));

  document.querySelectorAll(".format-grid button").forEach(b=>b.addEventListener("click",()=>b.classList.toggle("selected")));

  document.getElementById("generate-pack")?.addEventListener("click",()=>{
    const selected=[...document.querySelectorAll(".format-grid button.selected")].map(x=>x.textContent);
    const all=[...new Set([...selected,"Headline","Summary","Source trail","Platform copy"])];
    document.getElementById("pack-list").innerHTML=all.map(x=>'<div class="pack-item"><b>'+x+'</b><span>Ready ✓</span></div>').join("");
    showToast("Story Pack generated");
  });

  document.getElementById("save-story")?.addEventListener("click",()=>{
    const list=document.getElementById("stories-list");
    if(list && !list.querySelector('[data-saved-story="true"]')){
      const row=document.createElement("article");
      row.className="newsroom-row";
      row.dataset.savedStory="true";
      row.dataset.status="active";
      row.dataset.topic="entertainment";
      row.dataset.score="90";
      row.dataset.title=currentStoryTitle;
      row.dataset.source=currentUrl||"New source";
      row.innerHTML='<div class="story-cell-main"><span class="story-signal">90</span><div><b>'+currentStoryTitle+'</b><small>Saved just now · New story</small></div></div><div class="source-cell"><b>New source</b><small>Indexed</small></div><div><span class="desk-status active">Active</span></div><div><span class="guard-badge pass">✓ Supported</span></div><div class="output-count"><b>0</b><small>assets</small></div><div><span class="publish-state drafting">Drafting</span></div><div><button class="row-action" data-open-story>Open →</button></div>';
      row.querySelector("[data-open-story]").addEventListener("click",()=>openWorkspace(currentStoryTitle,currentUrl||"New source",currentUrl));
      list.prepend(row);
      initStoryDesk();
    }
    showToast("Story saved to newsroom");
  });

  let deskInitialized=false;
  function initStoryDesk(){
    const rows=[...document.querySelectorAll("#stories-list .newsroom-row")];
    const search=document.getElementById("story-search-input");
    const topic=document.getElementById("story-topic-filter");
    const sort=document.getElementById("story-sort");
    const tabs=[...document.querySelectorAll("[data-story-tab]")];
    let status="all";

    const apply=()=>{
      const q=(search?.value||"").trim().toLowerCase();
      const topicValue=topic?.value||"all";
      rows.forEach(row=>{
        const matchesStatus=status==="all"||row.dataset.status===status;
        const matchesTopic=topicValue==="all"||row.dataset.topic===topicValue;
        const hay=(row.dataset.title+" "+row.dataset.source).toLowerCase();
        row.hidden=!(matchesStatus&&matchesTopic&&(!q||hay.includes(q)));
      });
      const visible=rows.filter(r=>!r.hidden);
      const count=document.getElementById("story-visible-count");
      if(count)count.textContent=visible.length;
      const empty=document.getElementById("story-empty-filter");
      if(empty)empty.hidden=visible.length!==0;
    };

    const reorder=()=>{
      const list=document.getElementById("stories-list");
      const mode=sort?.value||"updated";
      const sorted=[...rows].sort((a,b)=>{
        if(mode==="score") return Number(b.dataset.score)-Number(a.dataset.score);
        if(mode==="title") return a.dataset.title.localeCompare(b.dataset.title);
        return 0;
      });
      sorted.forEach(r=>list.appendChild(r));
      apply();
    };

    if(!deskInitialized){
      search?.addEventListener("input",apply);
      topic?.addEventListener("change",apply);
      sort?.addEventListener("change",reorder);
      tabs.forEach(tab=>tab.addEventListener("click",()=>{
        tabs.forEach(t=>t.classList.remove("active"));
        tab.classList.add("active");
        status=tab.dataset.storyTab;
        apply();
      }));
      document.querySelectorAll("[data-jump-review]").forEach(btn=>btn.addEventListener("click",()=>{
        openView("stories");
        const reviewTab=document.querySelector('[data-story-tab="review"]');
        tabs.forEach(t=>t.classList.remove("active"));
        reviewTab?.classList.add("active");
        status="review";
        apply();
      }));
      document.getElementById("load-more-stories")?.addEventListener("click",()=>showToast("More stories will load from the backend."));
      deskInitialized=true;
    }
    apply();
  }

  initStoryDesk();
});