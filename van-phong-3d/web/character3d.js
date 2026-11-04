/* Văn Phòng 3D — Character3DRigController: rig 17 xương + chibi fallback, dáng đi cơ sinh học.
 * API: cloneSkinnedGltf(src) | create(root, clips, opts) | createProcedural(parts, opts) | measureSpeed(st, x, z, dt)
 * Controller: setPose('walk'|'stand'|'sit_work'|'sit_relax'|'sit_read'|'sit_desk'|'sit'|'play'), update(dt, {speed, lookYaw, seatY}) */
(function () {
  'use strict';
  const T = window.THREE;
  if (!T) return;
  const FADE = 0.28;
  const CLIP_FALLBACK = {
    walk: ['walk'], stand: ['stand', 'idle'], play: ['play', 'stand', 'idle'],
    sit_work: ['sit_work', 'sit_desk', 'sit', 'sit_read', 'sit_relax'],
    sit_relax: ['sit_relax', 'sit_read', 'sit', 'sit_work', 'sit_desk'],
    sit_read: ['sit_read', 'sit_relax', 'sit', 'sit_desk', 'sit_work'],
    sit_desk: ['sit_desk', 'sit_work', 'sit', 'sit_read', 'sit_relax'],
    sit: ['sit', 'sit_desk', 'sit_work', 'sit_read', 'sit_relax']
  };
  const BONE_ALIASES = {
    hips: ['hips', 'pelvis'], spine: ['spine'], chest: ['chest', 'spine1', 'spine2', 'upperchest'], neck: ['neck'], head: ['head'],
    upperArmL: ['upperarml', 'leftarm', 'upperarmleft'], forearmL: ['forearml', 'leftforearm', 'lowerarml'],
    handL: ['handl', 'lefthand'], upperArmR: ['upperarmr', 'rightarm', 'upperarmright'],
    forearmR: ['forearmr', 'rightforearm', 'lowerarmr'], handR: ['handr', 'righthand'],
    thighL: ['thighl', 'leftupleg', 'upperlegl'], shinL: ['shinl', 'leftleg', 'lowerlegl', 'calfl'],
    footL: ['footl', 'leftfoot'], thighR: ['thighr', 'rightupleg', 'upperlegr'],
    shinR: ['shinr', 'rightleg', 'lowerlegr', 'calfr'], footR: ['footr', 'rightfoot']
  };
  const norm = (n) => (n || '').toLowerCase().replace(/^mixamorig[:_]?/, '').replace(/[^a-z0-9]/g, '');
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const damp = (dt, rate) => 1 - Math.exp(-rate * dt);
  const AX = new T.Vector3(1, 0, 0), AY = new T.Vector3(0, 1, 0), AZ = new T.Vector3(0, 0, 1);
  const _q = new T.Quaternion(), _pq = new T.Quaternion(), _rq = new T.Quaternion();
  const _v = new T.Vector3(), _a = new T.Vector3(), _b = new T.Vector3(), _c = new T.Vector3();

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

  // Xoay xương quanh trục tính trong không gian model (độc lập trục local của từng rig)
  function rotateInRoot(root, bone, axis, angle) {
    if (!bone || !bone.parent || !angle) return;
    root.getWorldQuaternion(_rq); bone.parent.getWorldQuaternion(_pq);
    _v.copy(axis).applyQuaternion(_rq).applyQuaternion(_pq.invert());
    bone.quaternion.premultiply(_q.setFromAxisAngle(_v.normalize(), angle));
  }
  function localPos(root, bone, out) {
    return root.worldToLocal(bone.getWorldPosition(out));
  }

  function create(root, clips, opts) {
    opts = opts || {}; const mixer = opts.mixer || new T.AnimationMixer(root);
    const actions = opts.actions || {};
    (clips || []).forEach((clip) => {
      if (!actions[clip.name]) { const a = mixer.clipAction(clip); a.setLoop(T.LoopRepeat, Infinity); actions[clip.name] = a; }
    });
    Object.values(actions).forEach((a) => sealLoop(a.getClip()));
    const names = Object.assign({}, opts.clipNames || {});
    const bones = findBones(root);
    const smoothKeys = ['hips', 'spine', 'chest', 'neck', 'head'].filter((k) => bones[k]), prevQ = {};
    smoothKeys.forEach((k) => { prevQ[k] = bones[k].quaternion.clone(); });
    const st = { pose: '', clip: '', blendT: 1, walkW: 0, uprightW: 0, look: 0, ts: 1 };

    const resolve = (kind) => [names[kind]].concat(CLIP_FALLBACK[kind] || [kind]).find((n) => n && actions[n]) || null;
    const walkName = resolve('walk'), walkDur = walkName ? actions[walkName].getClip().duration : 1;
    // Tốc độ sải tự nhiên = chiều dài 1 chu kỳ bước / thời lượng clip  ->  timeScale = v / strideSpeed
    const strideSpeed = opts.strideSpeed || (opts.strideLength ? opts.strideLength / walkDur : 0.72);

    function setPose(kind) {
      const name = resolve(kind); st.pose = kind;
      if (!name || name === st.clip) return;
      const next = actions[name], prev = actions[st.clip];
      next.reset(); next.timeScale = kind === 'walk' ? st.ts : 1; next.setEffectiveWeight(1); next.play();
      if (prev) prev.crossFadeTo(next, FADE, false);
      if (kind === 'walk' && opts.randomPhase !== false && !prev) next.time = Math.random() * walkDur;
      st.clip = name; st.blendT = 0;
    }

    function postFix(dt, p) {
      const k = damp(dt, 6.5);
      st.walkW += ((st.pose === 'walk' ? 1 : 0) - st.walkW) * k;
      st.uprightW += ((/^sit/.test(st.pose) ? 0 : 1) - st.uprightW) * k;
      // 1) Làm mượt hông / cột sống / đầu khi đổi pha sit <-> walk <-> stand
      const f = damp(dt, 14);
      if (st.blendT < FADE + 0.12) smoothKeys.forEach((key) => { bones[key].quaternion.copy(prevQ[key].slerp(bones[key].quaternion, f)); });
      const w = st.walkW, b = bones;
      if (w > 0.01 && b.footL && b.footR && b.hips) {
        localPos(root, b.footL, _a); localPos(root, b.footR, _b);
        const sn = clamp((_a.z - _b.z) / 0.3, -1, 1);   // >0: chân trái đang ở trước
        const hn = clamp((_a.y - _b.y) / 0.08, -1, 1);  // >0: chân trái đang nhấc
        // 2) Lắc hông: xoay chậu theo chân bước + hạ nhẹ hông phía chân đang nhấc (pelvic sway)
        rotateInRoot(root, b.hips, AY, -0.07 * sn * w);
        rotateInRoot(root, b.hips, AZ, -0.035 * hn * w);
        // 3) Ngực xoay đối pha với chậu, cổ giữ đầu ổn định theo hướng đi
        rotateInRoot(root, b.chest || b.spine, AY, 0.11 * sn * w);
        rotateInRoot(root, b.neck || b.head, AY, -0.04 * sn * w);
        // 4) Vung tay đối pha chân + gập khuỷu nhẹ
        rotateInRoot(root, b.upperArmL, AX, 0.07 * sn * w);
        rotateInRoot(root, b.upperArmR, AX, -0.07 * sn * w);
        rotateInRoot(root, b.forearmL, AX, -0.12 * w);
        rotateInRoot(root, b.forearmR, AX, -0.12 * w);
        // 5) Gối: không duỗi khóa ở chân trụ, gập thêm ở pha lăng chân (swing)
        fixKnee(b.thighL, b.shinL, b.footL, 0.07 + Math.max(0, hn) * 0.22, w);
        fixKnee(b.thighR, b.shinR, b.footR, 0.07 + Math.max(0, -hn) * 0.22, w);
      }
      // 6) Kẹp góc vai: tay sát thân, không dang chữ A/T, không chĩa thẳng ra trước bụng
      if (st.uprightW > 0.01) { clampArm(b.upperArmL, b.forearmL, 1, st.uprightW); clampArm(b.upperArmR, b.forearmR, -1, st.uprightW); }
      // 7) Đầu nhìn theo hướng cần nhìn (lookYaw tương đối thân, giới hạn ±0.6 rad)
      st.look += (clamp(p.lookYaw || 0, -0.6, 0.6) - st.look) * damp(dt, 5);
      if (Math.abs(st.look) > 0.002) rotateInRoot(root, b.head || b.neck, AY, st.look);
      smoothKeys.forEach((key) => prevQ[key].copy(bones[key].quaternion));
    }

    function fixKnee(thigh, shin, foot, minFlex, w) {
      if (!thigh || !shin || !foot) return;
      localPos(root, thigh, _a); localPos(root, shin, _b); localPos(root, foot, _c);
      const flex = Math.atan2(_b.z - _a.z, _a.y - _b.y) - Math.atan2(_c.z - _b.z, _b.y - _c.y);
      if (flex < minFlex) rotateInRoot(root, shin, AX, (minFlex - flex) * w);
    }

    function clampArm(upper, fore, side, w) {
      if (!upper || !fore) return;
      localPos(root, upper, _a); localPos(root, fore, _b);
      const dx = _b.x - _a.x, dy = _a.y - _b.y, dz = _b.z - _a.z;
      const abd = Math.atan2(side * dx, dy), fwd = Math.atan2(dz, dy);
      const maxAbd = opts.maxShoulderAbduction || 0.3, maxFwd = opts.maxShoulderFlexion || 0.6;
      if (abd > maxAbd) rotateInRoot(root, upper, AZ, -side * (abd - maxAbd) * w);
      if (fwd > maxFwd) rotateInRoot(root, upper, AX, (fwd - maxFwd) * w);
    }

    function update(dt, p) {
      p = p || {}; dt = Math.min(Math.max(dt || 0, 0), 0.1); st.blendT += dt;
      const wa = walkName && actions[walkName];
      if (wa) {
        const v = p.speed !== undefined ? p.speed : (st.pose === 'walk' ? strideSpeed : 0);
        const target = clamp(v / strideSpeed, 0.35, 3.0);
        st.ts += (target - st.ts) * damp(dt, 10);
        wa.timeScale = st.ts;
      }
      mixer.update(dt); root.updateMatrixWorld(true); postFix(dt, p);
      if (p.seatY !== undefined && /^sit/.test(st.pose) && bones.hips && root.parent) {
        bones.hips.getWorldPosition(_a); root.parent.getWorldScale(_b);
        root.position.y += ((p.seatY - _a.y) / (_b.y || 1)) * damp(dt, 8);
      }
      return { bobY: 0 };
    }

    return { kind: 'skinned', root, mixer, actions, bones, strideSpeed, setPose, update, get pose() { return st.pose; }, get clip() { return st.clip; } };
  }

  // Fallback chibi (không có GLB): khớp hình học leftLeg/rightLeg/leftArm/rightArm/head, cùng API
  function createProcedural(parts, opts) {
    opts = opts || {}; const stepLen = opts.stepLength || 0.22;
    const st = { pose: 'stand', phase: Math.random() * 6.28, t: 0, w: { walk: 0, stand: 1, sit: 0, play: 0 } };
    const setPose = (kind) => { st.pose = kind; };
    function update(dt, p) {
      p = p || {}; dt = Math.min(Math.max(dt || 0, 0), 0.1); st.t += dt;
      const group = /^sit/.test(st.pose) ? 'sit' : (st.w[st.pose] !== undefined ? st.pose : 'stand');
      const k = damp(dt, 1 / FADE * 2.5);
      Object.keys(st.w).forEach((g) => { st.w[g] += ((g === group ? 1 : 0) - st.w[g]) * k; });
      const v = p.speed !== undefined ? p.speed : (group === 'walk' ? 0.6 : 0);
      st.phase += Math.PI * (v / stepLen) * dt;   // 1 chu kỳ = 2 bước -> khớp vận tốc, không trượt chân
      const s = Math.sin(st.phase), W = st.w, t = st.t;
      const legW = s * 0.55 * W.walk + Math.sin(t * 4.5) * 0.12 * W.play - (Math.PI / 2.2) * W.sit;
      const legR = -s * 0.55 * W.walk - Math.sin(t * 4.5) * 0.12 * W.play - (Math.PI / 2.2) * W.sit;
      if (parts.leftLeg) parts.leftLeg.rotation.x = legW; if (parts.rightLeg) parts.rightLeg.rotation.x = legR;
      if (parts.leftArm) {
        parts.leftArm.rotation.x = -s * 0.3 * W.walk + 0.05 * W.sit;
        parts.leftArm.rotation.z = clamp(-Math.sin(t * 4.2) * 0.18 * W.play, -0.12, 0.12);
      }
      if (parts.rightArm) {
        parts.rightArm.rotation.x = s * 0.3 * W.walk + 0.05 * W.sit;
        parts.rightArm.rotation.z = clamp(Math.sin(t * 6.5) * 0.3 * W.play, -0.12, 0.3);
      }
      if (parts.head) { parts.head.rotation.y = clamp(p.lookYaw || 0, -0.6, 0.6) * 0.5 + Math.sin(t * 0.9) * 0.06 * W.stand; parts.head.rotation.z = Math.sin(t * 2.8) * 0.08 * W.play; }
      return { bobY: Math.abs(Math.cos(st.phase)) * 0.025 * W.walk + Math.abs(Math.sin(t * 4.5)) * 0.03 * W.play };
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

  window.Character3DRigController = { cloneSkinnedGltf, create, createProcedural, measureSpeed, sealLoop, findBones, FADE };
})();
