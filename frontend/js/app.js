const API='/api';
async function api(path,opts={}){const r=await fetch(API+path,{headers:{'Content-Type':'application/json',...(opts.headers||{})},...opts});let d={};try{d=await r.json()}catch(e){}if(!r.ok)throw new Error(d.error||'Request failed');return d}
function toast(msg){const x=document.createElement('div');x.className='toast';x.textContent=msg;document.body.appendChild(x);setTimeout(()=>x.remove(),2500)}
async function getMe(){try{return (await api('/me')).user}catch(e){return null}}
function nav(){return `<nav class="nav"><div class="container nav-inner"><a class="logo" href="/"><span>●</span> CuisineHub</a><div class="navlinks"><a href="/recipes.html">Recipes</a><a href="/subscription.html">Premium</a><a href="/favorites.html" class="hide-mobile">Favorites</a><a href="/profile.html" class="hide-mobile">Profile</a><a href="/login.html" id="authLink">Login</a></div></div></nav>`}
function footer(){return `<footer class="footer"><div class="container">CuisineHub • Multi-Cuisine Recipe & Nutrition Guide • Mini Project</div></footer>`}
async function mount(){document.querySelector('#nav')?.insertAdjacentHTML('afterbegin',nav());document.querySelector('#footer')?.insertAdjacentHTML('beforeend',footer());const u=await getMe();const l=document.querySelector('#authLink');if(l&&u){l.textContent='Logout';l.href='#';l.onclick=async e=>{e.preventDefault();await api('/logout',{method:'POST'});location.href='/'};}startActivityTracking();}
let activityTimer=null;
async function trackActivity(){try{await api('/activity',{method:'POST',body:JSON.stringify({path:location.pathname})})}catch(e){}}
function startActivityTracking(){if(activityTimer)return;trackActivity();activityTimer=setInterval(trackActivity,15000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)trackActivity()})}
function card(r){return `<article class="card"><img src="${r.image_url}" alt="${r.name}"><div class="card-body"><span class="badge">${r.cuisine}</span> ${r.is_premium?'<span class="badge premium">PREMIUM</span>':''}<h3>${r.name}</h3><div class="meta"><span>⏱ ${r.prep_time} min</span><span>💪 ${r.protein}g</span><span>⭐ ${r.rating||0}</span></div><p class="muted">${r.description||''}</p><div class="card-actions"><a class="btn" href="/recipe.html?id=${r.id}">View Recipe</a><button class="btn ghost" onclick="toggleFav(${r.id})">♡</button></div></div></article>`}
async function toggleFav(id){try{await api('/favorites/'+id,{method:'POST'});toast('Saved to favorites')}catch(e){toast(e.message)}}
async function home(){const el=document.querySelector('#featured');if(!el)return;try{const d=await api('/recipes?high_protein=1');el.innerHTML=d.recipes.slice(0,6).map(card).join('')}catch(e){el.innerHTML='<div class="empty">Start MySQL and refresh the page.</div>'}}
async function setupAuth(){const form=document.querySelector('#authForm');if(!form)return;form.onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(form));try{const d=await api(form.dataset.mode==='register'?'/register':'/login',{method:'POST',body:JSON.stringify(data)});toast(d.message||'Success');setTimeout(()=>location.href='/',500)}catch(err){document.querySelector('#msg').textContent=err.message;document.querySelector('#msg').className='alert'}}}
async function setupRecipes(){const list=document.querySelector('#recipeList');if(!list)return;const initial=new URLSearchParams(location.search);for(const id of ['q','cuisine','diet','category','max_time']){const el=document.querySelector('#'+id);const v=initial.get(id);if(el&&v)el.value=v}if(initial.get('high_protein')==='1'&&document.querySelector('#high'))document.querySelector('#high').checked=true;const load=async()=>{const p=new URLSearchParams();for(const id of ['q','cuisine','diet','category','max_time']){const v=document.querySelector('#'+id)?.value;if(v)p.set(id,v)}if(document.querySelector('#high')?.checked)p.set('high_protein','1');try{const d=await api('/recipes?'+p);list.innerHTML=d.recipes.length?d.recipes.map(card).join(''):'<div class="empty">No recipes match your filters.</div>'}catch(e){list.innerHTML='<div class="empty">'+e.message+'</div>'}};document.querySelector('#searchBtn').onclick=load;['q','cuisine','diet','category','max_time','high'].forEach(id=>document.querySelector('#'+id)?.addEventListener('change',load));load()}
async function setupRecipe(){const id=new URLSearchParams(location.search).get('id');if(!id)return;try{const d=await api('/recipes/'+id);renderRecipe(d);loadReviews(id);if(!d.locked){try{const y=await api('/recipes/'+id+'/youtube');const block=document.querySelector('#youtubeVideo');if(block)block.innerHTML=youtubeVideoBlock(d.recipe.name,y.video_url,d.recipe.image_url)}catch(e){}}}catch(e){document.querySelector('#content').innerHTML='<div class="empty">'+e.message+'</div>'}}
function getYouTubeVideoId(url){
  const value=String(url||'').trim();
  if(!value)return '';
  try{
    const u=new URL(value,window.location.origin);
    const host=u.hostname.replace('www.','').toLowerCase();
    if(host==='youtu.be') return u.pathname.replace('/','').split('/')[0]||'';
    if(host==='youtube.com'||host==='m.youtube.com'||host==='youtube-nocookie.com'){
      if(u.searchParams.get('v')) return u.searchParams.get('v');
      const m=u.pathname.match(/\/(?:embed|shorts|live)\/([^/?]+)/);
      return m?m[1]:'';
    }
  }catch(e){}
  const m=value.match(/(?:v=|youtu\.be\/|\/embed\/|\/shorts\/|\/live\/)([A-Za-z0-9_-]{6,})/);
  return m?m[1]:'';
}
function youtubeVideoBlock(name,url,imageUrl){
  const id=getYouTubeVideoId(url) || '';
  const safeName=String(name||'Recipe').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const search='https://www.youtube.com/results?search_query='+encodeURIComponent((name || 'recipe')+' recipe');
  const fallbackThumb=imageUrl || 'https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=1200&q=80';
  const thumb=id ? ('https://i.ytimg.com/vi/'+encodeURIComponent(id)+'/hqdefault.jpg') : fallbackThumb;
  const watch=id ? ('https://www.youtube.com/watch?v='+encodeURIComponent(id)) : search;
  return `<div class="youtube-card" style="overflow:hidden;border-radius:18px;background:#0b1020;border:1px solid #26324d;box-shadow:0 10px 28px rgba(0,0,0,.25)">
    <div style="position:relative;aspect-ratio:16/9;background:#111827;overflow:hidden">
      <img src="${thumb}" alt="${safeName} YouTube thumbnail" style="display:block;width:100%;height:100%;object-fit:cover">
      <div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.05),rgba(0,0,0,.55));display:flex;align-items:center;justify-content:center">
        <div style="width:76px;height:54px;border-radius:16px;background:#ff0000;display:flex;align-items:center;justify-content:center;box-shadow:0 8px 24px rgba(0,0,0,.4)"><span style="color:#fff;font-size:30px;line-height:1;margin-left:4px">▶</span></div>
      </div>
      ${id ? '' : '<div style="position:absolute;left:16px;bottom:14px;background:rgba(0,0,0,.72);color:#fff;padding:7px 10px;border-radius:999px;font-size:.82rem">YouTube search preview</div>'}
    </div>
    <div style="padding:18px">
      <div style="font-weight:800;font-size:1.08rem;margin-bottom:6px">${safeName}</div>
      <div class="muted" style="margin-bottom:16px">${id ? 'Watch this cooking tutorial on YouTube.' : 'Find a step-by-step YouTube tutorial for this recipe.'}</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
        <a class="btn" href="${watch}" target="_blank" rel="noopener noreferrer">▶ Watch on YouTube</a>
        <a class="btn secondary" href="${search}" target="_blank" rel="noopener noreferrer">Find More Videos</a>
        <span class="muted" style="margin-left:auto">Opens YouTube in a new tab</span>
      </div>
    </div>
  </div>`;
}

function renderRecipe(d){
  const r=d.recipe;
  const videoBlock=youtubeVideoBlock(r.name,r.video_url,r.image_url);
  document.querySelector('#content').innerHTML=`<div class="detail"><div><img src="${r.image_url}" alt="${r.name}"></div><div><span class="badge">${r.cuisine} • ${r.diet}</span> ${r.is_premium?'<span class="badge premium">Premium</span>':''}<h1>${r.name}</h1><p class="muted">${r.description}</p><div class="nutrition"><div class="nut"><b>${r.calories}</b>Calories</div><div class="nut"><b>${r.protein}g</b>Protein</div><div class="nut"><b>${r.carbs}g</b>Carbs</div><div class="nut"><b>${r.fats}g</b>Fats</div></div>${d.locked?`<div class="lock"><h3>🔒 Premium recipe</h3><p class="muted">New users get 2 free premium recipe unlocks. After that choose a monthly plan.</p><button class="btn" onclick="unlock(${r.id})">Use Free Unlock</button> <a class="btn secondary" href="/subscription.html">View Plans</a></div>`:`<button class="btn" onclick="toggleFav(${r.id})">♡ Save Recipe</button><h2>Ingredients</h2><ul>${r.ingredients.split('\n').map(x=>'<li>'+x+'</li>').join('')}</ul><h2>Instructions</h2><ol>${r.instructions.split('\n').map(x=>'<li>'+x+'</li>').join('')}</ol><h2>Cooking Video</h2><div id="youtubeVideo">${videoBlock}</div>`}</div></div><div class="section"><div class="section-title"><h2>Community Reviews</h2><span class="muted">${r.rating||0}/5 average</span></div><div id="reviews"></div><form id="reviewForm"><div class="filters" style="grid-template-columns:120px 1fr auto"><select id="rating" class="select"><option value="5">5 ★</option><option value="4">4 ★</option><option value="3">3 ★</option><option value="2">2 ★</option><option value="1">1 ★</option></select><input id="comment" class="input" placeholder="Share your experience"><button class="btn">Post</button></div></form></div>`;
  document.querySelector('#reviewForm').onsubmit=async e=>{e.preventDefault();try{await api('/reviews/'+r.id,{method:'POST',body:JSON.stringify({rating:+document.querySelector('#rating').value,comment:document.querySelector('#comment').value})});toast('Review saved');loadReviews(r.id)}catch(err){toast(err.message)}}
}

async function unlock(id){try{const d=await api('/recipes/'+id+'/unlock',{method:'POST'});toast(d.free_trial_used?'Free unlock used':'Unlocked');setTimeout(()=>location.reload(),600)}catch(e){if(e.message.includes('Login'))location.href='/login.html';else toast(e.message)}}
async function loadReviews(id){try{const d=await api('/reviews/'+id);document.querySelector('#reviews').innerHTML=d.reviews.length?d.reviews.map(x=>`<div class="review"><b>${x.name}</b> <span class="stars">${'★'.repeat(x.rating)}${'☆'.repeat(5-x.rating)}</span><p class="muted">${x.comment||''}</p></div>`).join(''):'<p class="muted">No reviews yet.</p>'}catch(e){}}
async function setupFavorites(){const el=document.querySelector('#favList');if(!el)return;try{const d=await api('/favorites');el.innerHTML=d.recipes.length?d.recipes.map(card).join(''):'<div class="empty">No saved recipes yet.</div>'}catch(e){el.innerHTML='<div class="empty">Please login to view favorites.</div>'}}
async function setupProfile(){const el=document.querySelector('#profile');if(!el)return;const u=await getMe();if(!u){el.innerHTML='<div class="empty">Please login first.</div>';return}el.innerHTML=`<div class="formbox" style="margin:0"><h2>My Profile</h2><p class="muted">${u.email}</p><div class="field"><label>Name</label><input class="input" id="pname" value="${u.name}"></div><button class="btn" id="saveProfile">Save Changes</button><hr style="border-color:var(--border);margin:25px 0"><p>Plan: <b>${u.plan}</b></p><p>Selected cuisine: <b>${u.selected_cuisine||'All unlocked by Premium'}</b></p><p>Free recipe unlocks left: <b>${u.free_recipes_left}</b></p></div>`;document.querySelector('#saveProfile').onclick=async()=>{await api('/profile',{method:'PUT',body:JSON.stringify({name:document.querySelector('#pname').value})});toast('Profile updated')}}
async function setupSubscription(){const u=await getMe();document.querySelector('#currentPlan').textContent=u?`Current plan: ${u.plan} • Free unlocks left: ${u.free_recipes_left}`:'Login to activate a plan';document.querySelectorAll('[data-plan]').forEach(b=>b.onclick=async()=>{if(!u){location.href='/login.html';return}const plan=b.dataset.plan;let cuisine=null;if(plan==='CUISINE'){cuisine=document.querySelector('#planCuisine').value}try{await api('/subscription',{method:'POST',body:JSON.stringify({plan,cuisine})});toast('Plan activated');setTimeout(()=>location.href='/profile.html',600)}catch(e){toast(e.message)}})}
document.addEventListener('DOMContentLoaded',async()=>{await mount();home();setupAuth();setupRecipes();setupRecipe();setupFavorites();setupProfile();if(document.querySelector('#subscription'))setupSubscription()});
