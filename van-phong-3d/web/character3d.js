/* Văn Phòng 3D — Character3DRigController v8: Mocap Humanoid Retargeter + Multi-Harmonic Gait (cần mocap-gait.js).
 * Hỗ trợ rig 17 xương (hips, upper_arm.L...) và Mixamo / ReadyPlayerMe (Hips, Spine2, LeftArm, LeftUpLeg, LeftToeBase...).
 * API: cloneSkinnedGltf(src) | create(root, clips, opts) | createProcedural(parts, opts) | measureSpeed(st,x,z,dt) | stepYaw(...)
 * Controller: setPose('walk'|'stand'|'sit_work'|'sit_relax'|'sit_read'|'sit_desk'|'sit'|'play'), update(dt, {speed, lookYaw, turnRate, seatY}) */
(function () {
  'use strict';
  const T = window.THREE, G = window.MocapGait;
  if (!T || !G) return;
  const FADE = 0.28;
  const CLIP_FALLBACK = {
    walk: ['walk'], stand: ['stand', 'idle'], play: ['play', 'stand', 'idle'],
    sit_work: ['sit_work', 'sit_desk', 'sit', 'sit_read', 'sit_relax'], sit_relax: ['sit_relax', 'sit_read', 'sit', 'sit_work', 'sit_desk'],
    sit_read: ['sit_read', 'sit_relax', 'sit', 'sit_desk', 'sit_work'], sit_desk: ['sit_desk', 'sit_work', 'sit', 'sit_read', 'sit_relax'],
    sit: ['sit', 'sit_desk', 'sit_work', 'sit_read', 'sit_relax']
  };
  const A = (l, r) => [l, r];
  const SIDES = {
    shoulder: A(['shoulderl', 'leftshoulder', 'claviclel'], ['shoulderr', 'rightshoulder', 'clavicler']),
    upperArm: A(['upperarml', 'leftarm', 'upperarmleft'], ['upperarmr', 'rightarm', 'upperarmright']),
    forearm: A(['forearml', 'leftforearm', 'lowerarml'], ['forearmr', 'rightforearm', 'lowerarmr']),
    hand: A(['handl', 'lefthand'], ['handr', 'righthand']),
    thigh: A(['thighl', 'leftupleg', 'upperlegl'], ['thighr', 'rightupleg', 'upperlegr']),
    shin: A(['shinl', 'leftleg', 'lowerlegl', 'calfl'], ['shinr', 'rightleg', 'lowerlegr', 'calfr']),
    foot: A(['footl', 'leftfoot'], ['footr', 'rightfoot']),
    toe: A(['toel', 'lefttoebase', 'toesl', 'toebasel', 'lefttoe'], ['toer', 'righttoebase', 'toesr', 'toebaser', 'righttoe'])
  };
  const BONE_ALIASES = { hips: ['hips', 'pelvis'], spine: ['spine'], chest: ['chest', 'upperchest', 'spine2', 'spine1'], neck: ['neck'], head: ['head'] };
  Object.keys(SIDES).forEach((k) => { BONE_ALIASES[k + 'L'] = SIDES[k][0]; BONE_ALIASES[k + 'R'] = SIDES[k][1]; });
  const norm = (n) => (n || '').toLowerCase().replace(/^mixamorig\d*[:_]?/, '').replace(/[^a-z0-9]/g, '');
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const damp = (dt, rate) => 1 - Math.exp(-rate * dt);
  const wrapA = (a) => { while (a > Math.PI) a -= Math.PI * 2; while (a < -Math.PI) a += Math.PI * 2; return a; };
  const V3 = (x, y, z) => new T.Vector3(x, y, z);
  const _e = new T.Euler(), _q = new T.Quaternion(), _qf = new T.Quaternion(), _qs = new T.Quaternion(), _v = V3(), _s = V3();

  // Nhân bản đầy đủ SkinnedMesh + Skeleton + boneInverses (mỗi nhân vật một bộ xương riêng)
  function cloneSkinnedGltf(src) {
    const source = src && src.scene ? src.scene : src; source.updateMatrixWorld(true);
    const clone = source.clone(true), s = [], c = [];
    source.traverse((n) => s.push(n)); clone.traverse((n) => c.push(n));
    const map = new Map(s.map((n, i) => [n, c[i]]));
    s.forEach((n, i) => {
      if (!n.isSkinnedMesh || !c[i].isSkinnedMesh) return;
      c[i].bind(new T.Skeleton(n.skeleton.bones.map((b) => map.get(b) || b), n.skeleton.boneInverses.map((m) => m.clone())), n.bindMatrix.clone());
    });
    return clone;
  }

  // Chống khựng đầu/cuối chu kỳ: khóa keyframe cuối = keyframe đầu (bỏ qua track root-motion lệch lớn)
  function sealLoop(clip) {
    if (!clip || clip.userData_sealed) return; clip.userData_sealed = true;
    clip.tracks.forEach((tr) => {
      const n = tr.getValueSize(), v = tr.values, last = v.length - n;
      if (last <= 0) return;
      let maxD = 0, dot = 0;
      for (let k = 0; k < n; k++) { maxD = Math.max(maxD, Math.abs(v[last + k] - v[k])); dot += v[last + k] * v[k]; }
      if (maxD === 0 || maxD > (n === 4 ? 0.25 : 0.05)) return;
      const sign = n === 4 && dot < 0 ? -1 : 1; for (let k = 0; k < n; k++) v[last + k] = v[k] * sign;
    });
  }

  function findBones(root) {
    const byName = {};
    root.traverse((o) => { if (o.isBone) { const k = norm(o.name); if (!byName[k]) byName[k] = o; } });
    const out = {};
    Object.keys(BONE_ALIASES).forEach((key) => { out[key] = BONE_ALIASES[key].map((a) => byName[a]).find(Boolean) || null; });
    return out;
  }

  // Quaternion delta trong không gian root: E(x,y,z) * Flex(trục bản lề, f) * Hạ-tay/chân về tư thế tự nhiên
  function deltaQ(rec, d, scale, out) {
    out.setFromEuler(_e.set((d.x || 0) * scale, (d.y || 0) * scale, (d.z || 0) * scale, 'XYZ'));
    if (d.f && rec.axis) out.multiply(_qf.setFromAxisAngle(rec.axis, d.f * scale));
    return out;
  }
  // applyRootDeltaQ: local = P⁻¹ · D · P · base  (P = hướng rest của xương cha trong không gian root)
  const applyRootDeltaQ = (rec, D, base, out) => out.copy(rec.Pinv).multiply(D).multiply(rec.P).multiply(base);

  function create(root, clips, opts) {
    opts = opts || {}; const mixer = opts.mixer || new T.AnimationMixer(root);
    const actions = opts.actions || {};
    (clips || []).forEach((c) => { if (!actions[c.name]) { const a = mixer.clipAction(c); a.setLoop(T.LoopRepeat, Infinity); actions[c.name] = a; } });
    Object.values(actions).forEach((a) => sealLoop(a.getClip()));
    const names = Object.assign({}, opts.clipNames || {}), bones = findBones(root);
    // --- Lưu rest pose (restQ / restP / restWorldQ trong không gian root) của TẤT CẢ xương
    const all = [];
    root.traverse((o) => { if (o.isBone) all.push({ b: o, q: o.quaternion.clone(), p: o.position.clone(), sq: o.quaternion.clone(), sp: o.position.clone() }); });
    root.updateMatrixWorld(true);
    const invRoot = new T.Matrix4().copy(root.matrixWorld).invert();
    const rootM = (o) => new T.Matrix4().multiplyMatrices(invRoot, o.matrixWorld);
    const rootPos = (o) => V3(0, 0, 0).setFromMatrixPosition(rootM(o));
    const recs = {};
    Object.keys(bones).forEach((k) => {
      const b = bones[k]; if (!b || !b.parent) return;
      const pm = rootM(b.parent), P = new T.Quaternion(), restWorldQ = new T.Quaternion();
      pm.decompose(_v, P, _s); rootM(b).decompose(_v, restWorldQ, _s);
      recs[k] = { bone: b, restQ: b.quaternion.clone(), restP: b.position.clone(), restWorldQ, P, Pinv: P.clone().invert(),
        inv3: new T.Matrix3().setFromMatrix4(pm.clone().invert()), axis: null, down: null };
    });
    const dirOf = (a, b) => (bones[a] && bones[b] ? rootPos(bones[b]).sub(rootPos(bones[a])).normalize() : null);
    [['L', 1], ['R', -1]].forEach(([s, side]) => {
      const shin = recs['shin' + s], fore = recs['forearm' + s], ua = recs['upperArm' + s], th = recs['thigh' + s];
      const ds = dirOf('shin' + s, 'foot' + s), df = dirOf('forearm' + s, 'hand' + s);
      if (shin) shin.axis = ds ? ds.clone().cross(V3(0, 0, -1)).normalize() : V3(1, 0, 0);     // gối gập ra sau
      if (fore) fore.axis = df ? df.clone().cross(V3(0, 0, 1)).normalize() : V3(-side, 0, 0);  // khuỷu gập ra trước
      if (shin && shin.axis.lengthSq() < 0.5) shin.axis.set(1, 0, 0); if (fore && fore.axis.lengthSq() < 0.5) fore.axis.set(0, -side, 0);
      // Hạ tay từ T/A-pose về sát thân (dạng ~9°), chỉnh đùi thẳng đứng
      const du = dirOf('upperArm' + s, 'forearm' + s), dt0 = dirOf('thigh' + s, 'shin' + s);
      if (ua && du) ua.down = new T.Quaternion().setFromUnitVectors(du, V3(side * 0.16, -1, 0.02).normalize());
      if (th && dt0) th.down = new T.Quaternion().setFromUnitVectors(dt0, V3(side * 0.02, -1, 0).normalize());
    });
    const hipH = bones.hips ? Math.max(0.05, rootPos(bones.hips).y) : 0.95;
    const st = { pose: '', clip: '', synthW: 0, walkW: 0, phase: Math.random(), t: Math.random() * 50, amp: 0.8, lean: 0, bank: 0, look: 0, ts: 1 };

    const resolve = (kind) => [names[kind]].concat(CLIP_FALLBACK[kind] || [kind]).find((n) => n && actions[n]) || null;
    const walkName = resolve('walk'), walkDur = walkName ? actions[walkName].getClip().duration : 1;
    const strideSpeed = opts.strideSpeed || (opts.strideLength ? opts.strideLength / walkDur : 0.72);

    function setPose(kind) {
      const name = resolve(kind); st.pose = kind; if (!name || name === st.clip) return;
      const next = actions[name], prev = actions[st.clip];
      next.reset(); next.timeScale = kind === 'walk' ? st.ts : 1; next.setEffectiveWeight(1); next.play();
      if (prev) prev.crossFadeTo(next, FADE, false); st.clip = name;
    }

    const _D = new T.Quaternion(), _out = new T.Quaternion();
    function applySynth(spec, w) {
      Object.keys(recs).forEach((k) => {
        const rec = recs[k], d = spec[k]; if (!d && !rec.down) return;
        deltaQ(rec, d || {}, 1, _D); if (rec.down) _D.multiply(rec.down);
        rec.bone.quaternion.slerp(applyRootDeltaQ(rec, _D, rec.restQ, _out), w);
        if (k === 'hips' && d) {
          const sc = hipH / 0.95;
          _v.set((d.px || 0) * sc, (d.py || 0) * sc, (d.pz || 0) * sc).applyMatrix3(rec.inv3).add(rec.restP);
          rec.bone.position.lerp(_v, w);
        }
      });
    }
    function applyOverlay(spec, w) {
      Object.keys(spec).forEach((k) => {
        const rec = recs[k], d = spec[k]; if (!rec || !d) return;
        deltaQ(rec, d, w, _D);
        rec.bone.quaternion.copy(applyRootDeltaQ(rec, _D, _qs.copy(rec.bone.quaternion), _out));
        if (k === 'hips' && d.py) rec.bone.position.add(_v.set(0, d.py * w * hipH / 0.95, 0).applyMatrix3(rec.inv3));
      });
    }

    function update(dt, p) {
      p = p || {}; dt = Math.min(Math.max(dt || 0, 0), 0.1); st.t += dt;
      // 1) PropertyMixer chỉ ghi khi giá trị clip THAY ĐỔI -> trả mọi xương về đúng kết quả mixer khung trước
      //    (xương không có track = rest pose) rồi mới update, để lớp procedural không cộng dồn / kẹt tư thế cũ
      for (let i = 0; i < all.length; i++) { all[i].b.quaternion.copy(all[i].sq); all[i].b.position.copy(all[i].sp); }
      const upright = st.pose === 'walk' || st.pose === 'stand', k = damp(dt, 3 / FADE);
      st.synthW += ((upright ? 1 : 0) - st.synthW) * k;
      st.walkW += ((st.pose === 'walk' ? 1 : 0) - st.walkW) * k;
      // 2) Nhịp bước khóa theo vận tốc thật: 1 chu kỳ (2 bước) ≈ 1.65 × chiều cao hông (đo: chân trụ đứng yên trên sàn)
      root.getWorldScale(_s); const stride = (opts.strideFactor || 1.65) * hipH * (_s.y || 1), vNat = 0.95 * stride;
      const v = Math.max(0, p.speed !== undefined ? p.speed : (st.pose === 'walk' ? vNat : 0));
      st.amp += (clamp(v / vNat, 0.55, 1.15) - st.amp) * damp(dt, 4);
      st.lean += ((st.pose === 'walk' ? clamp(v / vNat, 0, 1.2) : 0) - st.lean) * damp(dt, 4);
      st.bank += (clamp(-(p.turnRate || 0) * 0.06, -0.12, 0.12) - st.bank) * damp(dt, 6);
      st.look += (clamp(p.lookYaw || 0, -0.6, 0.6) - st.look) * damp(dt, 5);
      if (st.pose === 'walk') st.phase = (st.phase + (v / (stride * (1.03 * st.amp - 0.035))) * dt) % 1; // sải thực ∝ biên độ (đo)
      const wa = walkName && actions[walkName];
      if (wa) { st.ts += (clamp(v / strideSpeed, 0.35, 3.0) - st.ts) * damp(dt, 10); wa.timeScale = st.ts; }
      mixer.update(dt);
      for (let i = 0; i < all.length; i++) { all[i].sq.copy(all[i].b.quaternion); all[i].sp.copy(all[i].b.position); }
      // 3) Tổng hợp dáng đi / đứng mocap đè lên clip (crossfade theo synthW), 4) lớp sống động cho ngồi / chơi
      const ctx = { amp: st.amp, lean: st.lean, bank: st.bank, look: st.look };
      if (st.synthW > 0.002) applySynth(G.blend(G.walk(st.phase, ctx), G.stand(st.t, ctx), st.walkW), st.synthW);
      if (st.synthW < 0.998) applyOverlay(G.overlay(st.pose, st.t, ctx), 1 - st.synthW);
      if (p.seatY !== undefined && /^sit/.test(st.pose) && bones.hips && root.parent) {
        root.updateMatrixWorld(true); bones.hips.getWorldPosition(_v); root.parent.getWorldScale(_s);
        root.position.y += ((p.seatY - _v.y) / (_s.y || 1)) * damp(dt, 8);
      }
      return { bobY: 0 };
    }

    return { kind: 'skinned', root, mixer, actions, bones, recs, strideSpeed, setPose, update, get pose() { return st.pose; }, get clip() { return st.clip; }, get phase() { return st.phase; } };
  }

  // Fallback chibi (không có GLB): dùng cùng đường cong mocap cho leftLeg/rightLeg/leftArm/rightArm/head
  function createProcedural(parts, opts) {
    opts = opts || {}; const stride = (opts.stepLength || 0.22) * 2;
    const st = { pose: 'stand', phase: Math.random(), t: Math.random() * 50, w: { walk: 0, sit: 0, play: 0 } };
    const setPose = (kind) => { st.pose = kind; };
    function update(dt, p) {
      p = p || {}; dt = Math.min(Math.max(dt || 0, 0), 0.1); st.t += dt;
      const g = /^sit/.test(st.pose) ? 'sit' : st.pose, k = damp(dt, 3 / FADE), W = st.w;
      Object.keys(W).forEach((n) => { W[n] += ((n === g ? 1 : 0) - W[n]) * k; });
      const v = p.speed !== undefined ? p.speed : (g === 'walk' ? 0.6 : 0);
      st.phase = (st.phase + (v / stride) * dt) % 1;
      const ctx = { amp: 1, lean: 0, bank: 0, look: clamp(p.lookYaw || 0, -0.6, 0.6) };
      const s = G.blend(G.walk(st.phase, ctx), G.stand(st.t, ctx), W.walk), t = st.t, sit = -(Math.PI / 2.2) * W.sit;
      if (parts.leftLeg) parts.leftLeg.rotation.x = s.thighL.x * 1.3 + Math.sin(t * 4.5) * 0.12 * W.play + sit;
      if (parts.rightLeg) parts.rightLeg.rotation.x = s.thighR.x * 1.3 - Math.sin(t * 4.5) * 0.12 * W.play + sit;
      if (parts.leftArm) { parts.leftArm.rotation.x = s.upperArmL.x * (1 - W.sit); parts.leftArm.rotation.z = -Math.sin(t * 4.2) * 0.12 * W.play; }
      if (parts.rightArm) { parts.rightArm.rotation.x = s.upperArmR.x * (1 - W.sit); parts.rightArm.rotation.z = Math.sin(t * 6.5) * 0.3 * W.play; }
      if (parts.head) { parts.head.rotation.y = s.head.y; parts.head.rotation.z = s.head.z + Math.sin(t * 2.8) * 0.08 * W.play; }
      return { bobY: -(s.hips.py || 0) * 0.5 * W.walk + 0.012 * W.walk + Math.abs(Math.sin(t * 4.5)) * 0.03 * W.play };
    }
    return { kind: 'procedural', setPose, update, get pose() { return st.pose; } };
  }

  // Vận tốc thực trên mặt sàn (m/s) từ vị trí thế giới giữa hai khung hình, có làm mượt
  function measureSpeed(state, x, z, dt) {
    if (state._px === undefined || !dt) { state._px = x; state._pz = z; state._v = 0; return 0; }
    const inst = Math.hypot(x - state._px, z - state._pz) / dt; state._px = x; state._pz = z;
    state._v += (Math.min(inst, 4) - state._v) * damp(dt, 12);
    return state._v;
  }
  // Xoay hướng mượt, độc lập FPS, giới hạn tốc độ xoay ở khúc cua -> { yaw, turnRate, lookYaw }
  function stepYaw(cur, target, dt, rate, maxRate) {
    const d = wrapA(target - cur), m = (maxRate || 3.2) * Math.max(dt, 1e-3);
    const step = clamp(d * damp(dt, rate || 7), -m, m);
    return { yaw: cur + step, turnRate: dt > 0 ? step / dt : 0, lookYaw: clamp(d - step, -0.6, 0.6) };
  }

  window.Character3DRigController = { cloneSkinnedGltf, create, createProcedural, measureSpeed, stepYaw, sealLoop, findBones, FADE, version: 8 };
})();
