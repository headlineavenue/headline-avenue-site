document.addEventListener("DOMContentLoaded",()=>{
  const views=[...document.querySelectorAll(".app-view")];
  const navBtns=[...document.querySelectorAll(".app-nav button")];
  const title=document.getElementById("view-title");
  const toast=document.getElementById("toast");
  const titles={home:"Radar",stories:"Stories",create:"Create",sources:"Sources",publish:"Publish",analytics:"Analytics"};
  let currentUrl="";
  let currentStoryTitle="Story detected from source";
  let currentSourceId=null;
  let currentStoryId=null;

  // Real API mode is intentionally enabled only when the static UI is served
  // locally. The public GitHub Pages demo stays prototype-only because an
  // HTTPS page should not make mixed-content requests to a localhost HTTP API.
  const localHosts=new Set(["localhost","127.0.0.1"]);
  const API_ORIGIN=localHosts.has(window.location.hostname)?"http://127.0.0.1:8000":"";
  const API_BASE=API_ORIGIN?API_ORIGIN+"/api/v1":"";

  async function apiRequest(path,options={}){
    if(!API_BASE)throw new Error("Real API mode requires the local frontend.");
    const response=await fetch(API_BASE+path,{
      headers:{"Content-Type":"application/json",...(options.headers||{})},
      ...options
    });
    if(!response.ok){
      let detail="";
      try{detail=JSON.stringify(await response.json())}catch{detail=await response.text()}
      throw new Error("API "+response.status+(detail?": "+detail:""));
    }
    if(response.status===204)return null;
    return response.json();
  }

  async function apiIsReady(){
    if(!API_ORIGIN)return false;
    try{
      const response=await fetch(API_ORIGIN+"/health");
      return response.ok;
    }catch{return false}
  }

  const showToast=m=>{toast.textContent=m;toast.classList.add("show");setTimeout(()=>toast.classList.remove("show"),1800)};

  function openView(name){
    views.forEach(v=>v.classList.remove("active"));
    document.getElementById("view-"+name)?.classList.add("active");
    navBtns.forEach(b=>b.classList.toggle("active",b.dataset.view===name));
    title.textContent=titles[name]||"Story Workspace";
  }

  navBtns.forEach(b=>b.addEventListener("click",()=>openView(b.dataset.view)));

  if(API_ORIGIN){
    apiIsReady().then(ready=>{
      if(ready)showToast("Local API connected");
      else showToast("Local UI ready — start the API on port 8000");
    });
  }

  function validYouTube(v){
    try{
      const u=new URL(v);
      return ["youtube.com","www.youtube.com","youtu.be","m.youtube.com"].includes(u.hostname);
    }catch{return false}
  }

  function openWorkspace(storyTitle,sourceLabel,url="",ids={}){
    currentUrl=url;
    currentStoryTitle=storyTitle||"Story detected from source";
    if(ids.sourceId!==undefined)currentSourceId=ids.sourceId;
    if(ids.storyId!==undefined)currentStoryId=ids.storyId;
    views.forEach(x=>x.classList.remove("active"));
    document.getElementById("story-workspace").classList.add("active");
    title.textContent="Story Workspace";
    document.getElementById("story-title").textContent=currentStoryTitle;
    document.getElementById("story-source-label").textContent=sourceLabel||url||"Indexed source";
    const save=document.getElementById("save-story");
    if(save)save.textContent=currentStoryId&&API_BASE?"Saved ✓":"Save story";
  }

  function analyze(v){
    if(!validYouTube(v)){showToast("Paste a valid YouTube URL.");return}
    openWorkspace("Story detected from YouTube source",v,v);
    showToast("Source indexed — demo workspace created");
  }

  document.getElementById("source-form")?.addEventListener("submit",e=>{e.preventDefault();analyze(document.getElementById("source-url").value.trim())});

  // Radar / live story intelligence
  const radarRows=[...document.querySelectorAll(".radar-signal")];
  const radarTabs=[...document.querySelectorAll("[data-radar-tab]")];
  const radarSearch=document.getElementById("radar-search-input");
  const radarVelocity=document.getElementById("radar-velocity-filter");
  let radarCategory="all";

  const applyRadarFilters=()=>{
    const q=(radarSearch?.value||"").trim().toLowerCase();
    const velocity=radarVelocity?.value||"all";
    radarRows.forEach(row=>{
      const categoryOk=radarCategory==="all"||row.dataset.radarCategory===radarCategory;
      const velocityOk=velocity==="all"||row.dataset.radarVelocity===velocity;
      const hay=(row.dataset.radarTitle+" "+row.dataset.radarSource+" "+row.dataset.radarCategory).toLowerCase();
      row.hidden=!(categoryOk&&velocityOk&&(!q||hay.includes(q)));
    });
    const empty=document.getElementById("radar-empty");
    if(empty)empty.hidden=radarRows.some(r=>!r.hidden);
  };

  radarTabs.forEach(tab=>tab.addEventListener("click",()=>{
    radarTabs.forEach(t=>t.classList.remove("active"));
    tab.classList.add("active");
    radarCategory=tab.dataset.radarTab;
    applyRadarFilters();
  }));
  radarSearch?.addEventListener("input",applyRadarFilters);
  radarVelocity?.addEventListener("change",applyRadarFilters);

  document.getElementById("radar-create-btn")?.addEventListener("click",()=>openView("create"));
  document.querySelectorAll("[data-radar-watch]").forEach(btn=>btn.addEventListener("click",()=>{
    const isWatching=btn.textContent==="Watching";
    btn.textContent=isWatching?"Watch":"Watching";
    showToast(isWatching?"Signal removed from watchlist":"Signal added to watchlist");
  }));
  document.querySelectorAll("[data-radar-watchlist]").forEach(btn=>btn.addEventListener("click",()=>showToast("Watchlist opened in prototype.")));
  document.getElementById("radar-manage-watchlists")?.addEventListener("click",()=>openView("sources"));
  document.getElementById("radar-load-more")?.addEventListener("click",()=>showToast("More live signals will load from the backend."));
  applyRadarFilters();

  // Story Studio / Create
  const sourceTypeButtons=[...document.querySelectorAll("[data-source-type]")];
  const sourcePanes=[...document.querySelectorAll("[data-source-pane]")];
  let createSourceType="url";
  let createBuildChoice="storypack";
  let createEditorialMode="balanced";

  const updateCreateSummary=()=>{
    const formats=[...document.querySelectorAll("[data-create-format].selected")].map(b=>b.dataset.createFormat);
    const label={storypack:"Full Story Pack",video:"Video",article:"Article",social:"Social package"}[createBuildChoice]||"Story Pack";
    const mode=createEditorialMode.charAt(0).toUpperCase()+createEditorialMode.slice(1);
    const summary=document.getElementById("create-summary");
    if(summary)summary.textContent=label+" · "+(formats.length?formats.join(" + "):"No video format")+" · "+mode;
    const guard=document.querySelector(".create-submit-row small");
    if(guard)guard.textContent=document.getElementById("create-sourceguard")?.checked?"SourceGuard enabled":"SourceGuard off";
  };

  sourceTypeButtons.forEach(btn=>btn.addEventListener("click",()=>{
    createSourceType=btn.dataset.sourceType;
    sourceTypeButtons.forEach(b=>b.classList.toggle("active",b===btn));
    sourcePanes.forEach(p=>p.classList.toggle("active",p.dataset.sourcePane===createSourceType));
  }));

  document.getElementById("sample-source")?.addEventListener("click",()=>{
    document.getElementById("create-source-url").value="https://www.youtube.com/watch?v=demo-spiderman";
  });
  document.querySelector("[data-fill-article]")?.addEventListener("click",()=>{
    document.getElementById("create-article-url").value="https://example.com/news/story";
  });

  [["create-file-upload","upload-file-name"],["create-audio-upload","audio-file-name"],["create-pdf-upload","pdf-file-name"]].forEach(([inputId,labelId])=>{
    document.getElementById(inputId)?.addEventListener("change",e=>{
      const file=e.target.files?.[0];
      const label=document.getElementById(labelId);
      if(label)label.textContent=file?file.name:"No file selected";
    });
  });

  document.getElementById("create-transcript")?.addEventListener("input",e=>{
    const counter=document.getElementById("transcript-count");
    if(counter)counter.textContent=e.target.value.length+" characters";
  });

  document.querySelectorAll("[data-build-choice]").forEach(btn=>btn.addEventListener("click",()=>{
    createBuildChoice=btn.dataset.buildChoice;
    document.querySelectorAll("[data-build-choice]").forEach(b=>b.classList.toggle("selected",b===btn));
    updateCreateSummary();
  }));

  document.querySelectorAll("[data-create-format]").forEach(btn=>btn.addEventListener("click",()=>{
    btn.classList.toggle("selected");
    updateCreateSummary();
  }));

  document.querySelectorAll("[data-editorial-mode]").forEach(btn=>btn.addEventListener("click",()=>{
    createEditorialMode=btn.dataset.editorialMode;
    document.querySelectorAll("[data-editorial-mode]").forEach(b=>b.classList.toggle("selected",b===btn));
    updateCreateSummary();
  }));

  document.getElementById("create-sourceguard")?.addEventListener("change",updateCreateSummary);

  document.querySelectorAll("[data-recent-url]").forEach(btn=>btn.addEventListener("click",()=>{
    createSourceType="url";
    sourceTypeButtons.forEach(b=>b.classList.toggle("active",b.dataset.sourceType==="url"));
    sourcePanes.forEach(p=>p.classList.toggle("active",p.dataset.sourcePane==="url"));
    const input=document.getElementById("create-source-url");
    if(input){input.value=btn.dataset.recentUrl;input.focus()}
    showToast("Recent source loaded");
  }));

  document.getElementById("create-builder-form")?.addEventListener("submit",async e=>{
    e.preventDefault();
    let sourceLabel="";
    let sourceUrl="";
    let sourceTitle="";
    let transcriptText=null;
    const metadata={
      build_choice:createBuildChoice,
      editorial_mode:createEditorialMode,
      sourceguard_enabled:Boolean(document.getElementById("create-sourceguard")?.checked)
    };

    if(createSourceType==="url"){
      sourceUrl=document.getElementById("create-source-url")?.value.trim()||"";
      let parsed;
      try{parsed=new URL(sourceUrl)}catch{showToast("Paste a valid source URL.");return}
      sourceTitle=(parsed.hostname.replace(/^www\./,"")||"Web")+" source";
      sourceLabel="Web source · "+sourceUrl;
    }else if(createSourceType==="article"){
      sourceUrl=document.getElementById("create-article-url")?.value.trim()||"";
      let parsed;
      try{parsed=new URL(sourceUrl)}catch{showToast("Paste a valid article URL.");return}
      sourceTitle=(parsed.hostname.replace(/^www\./,"")||"Article")+" article";
      sourceLabel="Article · "+sourceUrl;
    }else if(createSourceType==="upload"){
      const file=document.getElementById("create-file-upload")?.files?.[0];
      if(!file){showToast("Choose a video file first.");return}
      sourceTitle=file.name;
      sourceLabel="Video upload · "+file.name;
      metadata.filename=file.name;
      metadata.size=file.size;
      metadata.content_type=file.type;
    }else if(createSourceType==="audio"){
      const file=document.getElementById("create-audio-upload")?.files?.[0];
      if(!file){showToast("Choose an audio file first.");return}
      sourceTitle=file.name;
      sourceLabel="Audio upload · "+file.name;
      metadata.filename=file.name;
      metadata.size=file.size;
      metadata.content_type=file.type;
    }else if(createSourceType==="pdf"){
      const file=document.getElementById("create-pdf-upload")?.files?.[0];
      if(!file){showToast("Choose a PDF first.");return}
      sourceTitle=file.name;
      sourceLabel="PDF · "+file.name;
      metadata.filename=file.name;
      metadata.size=file.size;
      metadata.content_type=file.type;
    }else if(createSourceType==="transcript"){
      const text=document.getElementById("create-transcript")?.value.trim()||"";
      if(text.length<40){showToast("Add a little more source text first.");return}
      transcriptText=text;
      sourceTitle="Pasted transcript";
      sourceLabel="Transcript · "+text.length+" characters";
    }

    const buildLabel={storypack:"Story Pack",video:"Video story",article:"Article story",social:"Social story"}[createBuildChoice]||"Story";

    // Public GitHub Pages remains the polished prototype.
    if(!API_BASE){
      currentSourceId=null;
      currentStoryId=null;
      openWorkspace(buildLabel+" workspace",sourceLabel,sourceUrl);
      showToast("Prototype workspace created — run the UI locally for real persistence");
      return;
    }

    const submit=e.currentTarget.querySelector('button[type="submit"]');
    const originalText=submit?.textContent;
    if(submit){submit.disabled=true;submit.textContent="Building…"}

    try{
      if(!(await apiIsReady()))throw new Error("Headline Avenue API is not running on port 8000.");

      const source=await apiRequest("/sources",{
        method:"POST",
        body:JSON.stringify({
          workspace_slug:"headline-avenue",
          kind:createSourceType==="upload"?"video":createSourceType,
          title:sourceTitle||null,
          original_url:sourceUrl||null,
          transcript_text:transcriptText,
          metadata
        })
      });

      const story=await apiRequest("/stories",{
        method:"POST",
        body:JSON.stringify({
          workspace_slug:"headline-avenue",
          source_id:source.id,
          title:buildLabel+" from "+(sourceTitle||"source"),
          angle:createEditorialMode+" editorial treatment from the selected source.",
          signal_score:null
        })
      });

      openWorkspace(story.title,sourceLabel,sourceUrl,{sourceId:source.id,storyId:story.id});
      showToast("Saved to backend — Story Workspace created");
    }catch(error){
      console.error(error);
      showToast("Backend error — "+error.message);
    }finally{
      if(submit){submit.disabled=false;submit.textContent=originalText||"Build Story Workspace →"}
    }
  });

  updateCreateSummary();


  // Sources / intelligence library
  const sourceRows=[...document.querySelectorAll("#source-library-list .source-row")];
  const sourceTabs=[...document.querySelectorAll("[data-source-tab]")];
  const sourceSearch=document.getElementById("source-search-input");
  const sourceStatus=document.getElementById("source-status-filter");
  const sourceSort=document.getElementById("source-sort");
  let sourceTypeFilter="all";

  const applySourceFilters=()=>{
    const q=(sourceSearch?.value||"").trim().toLowerCase();
    const status=sourceStatus?.value||"all";
    sourceRows.forEach(row=>{
      const typeOk=sourceTypeFilter==="all"||row.dataset.type===sourceTypeFilter;
      const statusOk=status==="all"||row.dataset.status===status;
      const hay=(row.dataset.title+" "+row.dataset.origin+" "+row.dataset.type).toLowerCase();
      row.hidden=!(typeOk&&statusOk&&(!q||hay.includes(q)));
    });
    const visible=sourceRows.filter(r=>!r.hidden);
    const count=document.getElementById("source-visible-count");
    if(count)count.textContent=visible.length;
    const empty=document.getElementById("source-empty-filter");
    if(empty)empty.hidden=visible.length!==0;
  };

  sourceTabs.forEach(tab=>tab.addEventListener("click",()=>{
    sourceTabs.forEach(t=>t.classList.remove("active"));
    tab.classList.add("active");
    sourceTypeFilter=tab.dataset.sourceTab;
    applySourceFilters();
  }));
  sourceSearch?.addEventListener("input",applySourceFilters);
  sourceStatus?.addEventListener("change",applySourceFilters);
  sourceSort?.addEventListener("change",()=>{
    const list=document.getElementById("source-library-list");
    const mode=sourceSort.value;
    const sorted=[...sourceRows].sort((a,b)=>{
      if(mode==="stories")return Number(b.dataset.stories)-Number(a.dataset.stories);
      if(mode==="title")return a.dataset.title.localeCompare(b.dataset.title);
      return 0;
    });
    sorted.forEach(r=>list.appendChild(r));
    applySourceFilters();
  });

  document.getElementById("add-source-btn")?.addEventListener("click",()=>openView("create"));
  document.querySelectorAll("[data-source-create]").forEach(btn=>btn.addEventListener("click",()=>{
    openView("create");
    const url=btn.dataset.sourceUrl||"";
    const input=document.getElementById("create-source-url");
    sourceTypeButtons.forEach(b=>b.classList.toggle("active",b.dataset.sourceType==="url"));
    sourcePanes.forEach(p=>p.classList.toggle("active",p.dataset.sourcePane==="url"));
    createSourceType="url";
    if(input){input.value=url;input.focus()}
    showToast("Source loaded into Story Studio");
  }));
  document.querySelectorAll("[data-source-open]").forEach(btn=>btn.addEventListener("click",()=>{
    const row=btn.closest(".source-row");
    showToast((row?.dataset.title||"Source")+" opened — detail panel coming with backend.");
  }));
  document.querySelectorAll("[data-source-reindex]").forEach(btn=>btn.addEventListener("click",()=>{
    const row=btn.closest(".source-row");
    const state=row?.querySelector(".index-state");
    if(state){state.textContent="◌ Queued";state.className="index-state indexing"}
    btn.textContent="Queued";
    showToast("Source added to the indexing queue");
  }));
  document.querySelectorAll("[data-source-watch-toggle]").forEach(btn=>btn.addEventListener("click",()=>{
    const paused=btn.textContent==="Resume";
    btn.textContent=paused?"Pause":"Resume";
    showToast(paused?"Watchlist resumed":"Watchlist paused");
  }));
  document.querySelectorAll("[data-watch-demo]").forEach(btn=>btn.addEventListener("click",()=>showToast("Watchlist details will open here.")));
  document.getElementById("new-watchlist-btn")?.addEventListener("click",()=>showToast("Watchlist builder is next on the roadmap."));
  document.getElementById("load-more-sources")?.addEventListener("click",()=>showToast("More sources will load from the backend."));
  applySourceFilters();


  // Publisher / distribution desk
  const publishJobs=[...document.querySelectorAll(".publish-job")];
  const publishTabs=[...document.querySelectorAll("[data-publish-tab]")];
  let publishStatus="draft";
  let scheduleMode="now";

  const applyPublishFilter=()=>{
    publishJobs.forEach(job=>job.hidden=job.dataset.publishStatus!==publishStatus);
    const visible=publishJobs.filter(j=>!j.hidden);
    const empty=document.getElementById("publish-empty");
    if(empty)empty.hidden=visible.length!==0;
  };

  publishTabs.forEach(tab=>tab.addEventListener("click",()=>{
    publishTabs.forEach(t=>t.classList.remove("active"));
    tab.classList.add("active");
    publishStatus=tab.dataset.publishTab;
    applyPublishFilter();
  }));

  const updatePublisherButton=()=>{
    const checked=[...document.querySelectorAll("[data-publish-destination]:checked")];
    const btn=document.getElementById("publisher-submit");
    if(!btn)return;
    if(scheduleMode==="draft"){btn.textContent="Save as draft →";return}
    if(scheduleMode==="later"){btn.textContent="Schedule for "+checked.length+" destination"+(checked.length===1?"":"s")+" →";return}
    btn.textContent="Publish to "+checked.length+" destination"+(checked.length===1?"":"s")+" →";
  };

  document.querySelectorAll("[data-publish-destination]").forEach(cb=>cb.addEventListener("change",updatePublisherButton));

  document.querySelectorAll("[data-schedule-mode]").forEach(btn=>btn.addEventListener("click",()=>{
    scheduleMode=btn.dataset.scheduleMode;
    document.querySelectorAll("[data-schedule-mode]").forEach(b=>b.classList.toggle("selected",b===btn));
    const dt=document.getElementById("schedule-datetime");
    if(dt)dt.hidden=scheduleMode!=="later";
    const label=document.getElementById("publish-schedule-label");
    if(label)label.textContent=scheduleMode==="now"?"Publish now":scheduleMode==="later"?"Choose date and time":"Keep in newsroom";
    updatePublisherButton();
  }));

  document.querySelectorAll("[data-publish-open]").forEach(btn=>btn.addEventListener("click",()=>{
    const job=btn.closest(".publish-job");
    publishJobs.forEach(j=>j.classList.toggle("selected",j===job));
    const titleInput=document.getElementById("publish-title-input");
    if(titleInput)titleInput.value=job?.dataset.jobTitle||"";
    const state=document.querySelector(".inspector-state");
    if(state)state.textContent=(job?.dataset.publishStatus||"draft").toUpperCase();
    showToast("Publishing job loaded in inspector");
  }));

  document.querySelectorAll(".destination-card").forEach(card=>card.addEventListener("click",()=>{
    card.classList.toggle("active");
    if(card.dataset.destination==="tiktok"&&card.classList.contains("active"))showToast("TikTok is available in sandbox only in this prototype.");
  }));

  document.getElementById("compose-publish-btn")?.addEventListener("click",()=>{
    publishStatus="draft";
    publishTabs.forEach(t=>t.classList.toggle("active",t.dataset.publishTab==="draft"));
    applyPublishFilter();
    document.querySelector(".publisher-aside")?.scrollIntoView({behavior:"smooth",block:"start"});
    showToast("New publish job ready for review");
  });

  document.getElementById("manage-destinations")?.addEventListener("click",()=>showToast("Destination management will connect to authorized platform accounts."));

  document.getElementById("publisher-submit")?.addEventListener("click",()=>{
    const checked=[...document.querySelectorAll("[data-publish-destination]:checked")].map(x=>x.value);
    if(!checked.length){showToast("Choose at least one destination.");return}
    if(checked.includes("TikTok")){showToast("TikTok is sandbox-only until production access is approved.");return}
    if(scheduleMode==="later"){
      const date=document.getElementById("publish-date")?.value;
      const time=document.getElementById("publish-time")?.value;
      if(!date||!time){showToast("Choose a schedule date and time.");return}
      showToast("Publish job scheduled in the prototype");
      return;
    }
    if(scheduleMode==="draft"){showToast("Publish job saved as draft");return}
    showToast("Prototype ready — live publishing backend not connected yet");
  });

  document.getElementById("publisher-save-draft")?.addEventListener("click",()=>showToast("Publishing changes saved in this prototype."));
  updatePublisherButton();
  applyPublishFilter();


  // Analytics / editorial intelligence
  const analyticsData={
    "7d":{views:"486K",watch:"73%",engagement:"9.4%",packs:"8"},
    "30d":{views:"1.84M",watch:"71%",engagement:"8.9%",packs:"27"},
    "90d":{views:"4.92M",watch:"68%",engagement:"8.1%",packs:"71"}
  };
  const platformData={
    all:{views:"1.84M",watch:"71%",engagement:"8.9%"},
    youtube:{views:"846K",watch:"76%",engagement:"7.8%"},
    instagram:{views:"699K",watch:"68%",engagement:"10.6%"},
    tiktok:{views:"295K",watch:"70%",engagement:"8.3%"}
  };
  let analyticsPeriod="30d";
  let analyticsPlatform="all";

  const refreshAnalyticsMetrics=()=>{
    const period=analyticsData[analyticsPeriod];
    const platform=platformData[analyticsPlatform];
    const views=document.getElementById("metric-views");
    const watch=document.getElementById("metric-watch");
    const engagement=document.getElementById("metric-engagement");
    const packs=document.getElementById("metric-packs");
    if(views)views.textContent=analyticsPlatform==="all"?period.views:platform.views;
    if(watch)watch.textContent=analyticsPlatform==="all"?period.watch:platform.watch;
    if(engagement)engagement.textContent=analyticsPlatform==="all"?period.engagement:platform.engagement;
    if(packs)packs.textContent=period.packs;
  };

  document.querySelectorAll("[data-analytics-period]").forEach(btn=>btn.addEventListener("click",()=>{
    analyticsPeriod=btn.dataset.analyticsPeriod;
    document.querySelectorAll("[data-analytics-period]").forEach(b=>b.classList.toggle("active",b===btn));
    refreshAnalyticsMetrics();
    showToast("Analytics window changed to "+btn.textContent);
  }));

  document.getElementById("analytics-platform-filter")?.addEventListener("change",e=>{
    analyticsPlatform=e.target.value;
    refreshAnalyticsMetrics();
    showToast(e.target.options[e.target.selectedIndex].text+" analytics loaded");
  });

  document.querySelectorAll("[data-performance-story]").forEach(btn=>btn.addEventListener("click",()=>{
    showToast(btn.dataset.performanceStory+" performance detail will open here.");
  }));
  document.querySelectorAll("[data-recommendation]").forEach(btn=>btn.addEventListener("click",()=>{
    showToast("Recommendation saved for the next Story Pack.");
  }));
  document.getElementById("view-all-performance")?.addEventListener("click",()=>showToast("Full performance table will open here."));
  refreshAnalyticsMetrics();

  document.querySelectorAll("[data-create-demo]").forEach(b=>b.addEventListener("click",()=>openWorkspace("Story opportunity from Radar","Radar-discovered source")));
  document.getElementById("back-radar")?.addEventListener("click",()=>openView("stories"));
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

  document.getElementById("generate-pack")?.addEventListener("click",async()=>{
    const selected=[...document.querySelectorAll(".format-grid button.selected")].map(x=>x.textContent.trim());
    const normalized={
      "9:16":"9:16_video",
      "16:9":"16:9_video",
      "1:1":"1:1_video",
      "4:5":"4:5_video",
      "Article":"article",
      "Carousel":"carousel",
      "Newsletter":"newsletter",
      "Thread":"thread"
    };
    const requested=[...new Set([
      ...selected.map(x=>normalized[x]||x.toLowerCase().replace(/\s+/g,"_")),
      "headline","summary","source_trail","platform_copy"
    ])];

    const button=document.getElementById("generate-pack");
    const originalText=button?.textContent;
    if(button){button.disabled=true;button.textContent="Generating…"}

    const renderOutputs=outputs=>{
      const pretty=value=>value
        .replace(/_/g," ")
        .replace(/^\d+:\d+ video$/i,m=>m.replace(" video",""))
        .replace(/\b\w/g,c=>c.toUpperCase());
      document.getElementById("pack-list").innerHTML=outputs.map(output=>
        '<div class="pack-item"><b>'+pretty(output.output_type||output)+'</b><span>Ready ✓</span></div>'
      ).join("");
      const count=document.getElementById("story-output-count");
      if(count)count.textContent=outputs.length;
      const state=document.getElementById("story-pack-state");
      if(state){state.textContent="Ready";state.classList.add("verified-text")}
      const send=document.getElementById("send-to-publish");
      if(send)send.disabled=false;
    };

    try{
      if(API_BASE&&currentStoryId){
        const result=await apiRequest("/story-packs/generate",{
          method:"POST",
          body:JSON.stringify({story_id:currentStoryId,formats:requested})
        });
        renderOutputs(result.outputs||[]);
        showToast("Story Pack generated and saved to backend");
      }else{
        renderOutputs(requested);
        showToast("Story Pack generated in prototype mode");
      }
    }catch(error){
      console.error(error);
      showToast("Story Pack error — "+error.message);
    }finally{
      if(button){button.disabled=false;button.textContent=originalText||"Generate Story Pack"}
    }
  });

  document.getElementById("send-to-publish")?.addEventListener("click",()=>{
    openView("publish");
    showToast("Story Pack moved into the publishing desk");
  });

  document.getElementById("open-source-from-story")?.addEventListener("click",()=>{
    openView("sources");
    showToast("Source library opened");
  });

  document.getElementById("save-story")?.addEventListener("click",()=>{
    if(API_BASE&&currentStoryId){
      showToast("Story is already saved to the backend");
      return;
    }
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

  // Final interaction polish
  const selectStoryRow=(row)=>{
    document.querySelectorAll("#stories-list .newsroom-row").forEach(r=>r.classList.toggle("selected",r===row));
  };
  document.querySelectorAll("#stories-list .newsroom-row").forEach(row=>{
    row.addEventListener("click",e=>{
      if(e.target.closest("button,a,input,select,textarea"))return;
      selectStoryRow(row);
    });
    row.addEventListener("keydown",e=>{
      if(e.key==="Enter"||e.key===" "){e.preventDefault();selectStoryRow(row)}
    });
  });

  document.querySelectorAll("#source-library-list .source-row").forEach(row=>{
    row.tabIndex=0;
    row.addEventListener("click",e=>{
      if(e.target.closest("button,a,input,select,textarea"))return;
      document.querySelectorAll("#source-library-list .source-row").forEach(r=>r.classList.toggle("selected",r===row));
    });
    row.addEventListener("keydown",e=>{
      if(e.key==="Enter"||e.key===" "){
        e.preventDefault();
        document.querySelectorAll("#source-library-list .source-row").forEach(r=>r.classList.toggle("selected",r===row));
      }
    });
  });

  document.querySelectorAll("[data-recommendation]").forEach(btn=>btn.addEventListener("click",()=>{
    btn.classList.toggle("saved");
    if(btn.classList.contains("saved")) showToast("Recommendation saved for the next Story Pack.");
  }));

  document.querySelectorAll(".top-story-row").forEach(row=>row.addEventListener("mouseenter",()=>row.setAttribute("aria-label","Open performance detail for "+(row.dataset.performanceStory||"story"))));

  const firstStory=document.querySelector("#stories-list .newsroom-row");
  if(firstStory)firstStory.classList.add("selected");

  initStoryDesk();
});