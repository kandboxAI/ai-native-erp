<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { binary } from "../api";

const props = defineProps<{ url: string; highlightedFaces?: number[] }>();
const host = ref<HTMLDivElement>();
const loading = ref(false);
const error = ref("");
const selectedFace = ref<number | null>(null);
let renderer: THREE.WebGLRenderer;
let camera: THREE.PerspectiveCamera;
let scene: THREE.Scene;
let controls: OrbitControls;
let mesh: THREE.Mesh | null = null;
let faceIds: number[] = [];
let observer: ResizeObserver;
let animation = 0;
let generation = 0;

function highlight() {
  if (!mesh) return;
  const geometry = mesh.geometry as THREE.BufferGeometry;
  const colors = geometry.getAttribute("color") as THREE.BufferAttribute;
  const faces = props.highlightedFaces?.length
    ? props.highlightedFaces
    : [selectedFace.value];
  faceIds.forEach((face, triangle) => {
    const color = new THREE.Color(faces.includes(face) ? "#db8b25" : "#8498a8");
    for (let i = 0; i < 3; i++)
      colors.setXYZ(triangle * 3 + i, color.r, color.g, color.b);
  });
  colors.needsUpdate = true;
}

async function load() {
  if (!scene || !props.url) return;
  const current = ++generation;
  loading.value = true;
  error.value = "";
  try {
    // 网格由预览组件按需鉴权读取，避免预加载失败后只留下一个空地址。
    const response = await binary(props.url);
    const data = JSON.parse(await response.text());
    if (current !== generation) return;
    if (mesh) {
      scene.remove(mesh);
      mesh.geometry.dispose();
      (mesh.material as THREE.Material).dispose();
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(data.positions, 3),
    );
    geometry.setAttribute(
      "color",
      new THREE.Float32BufferAttribute(
        new Float32Array(data.positions.length),
        3,
      ),
    );
    geometry.computeVertexNormals();
    geometry.computeBoundingSphere();
    mesh = new THREE.Mesh(
      geometry,
      new THREE.MeshStandardMaterial({
        vertexColors: true,
        roughness: 0.62,
        metalness: 0.15,
        side: THREE.DoubleSide,
      }),
    );
    scene.add(mesh);
    faceIds = data.face_ids;
    const sphere = geometry.boundingSphere!;
    const distance = Math.max(sphere.radius * 3, 10);
    controls.target.copy(sphere.center);
    camera.position
      .copy(sphere.center)
      .add(new THREE.Vector3(distance, -distance, distance * 0.75));
    camera.far = Math.max(distance * 50, 1000);
    camera.updateProjectionMatrix();
    controls.update();
    selectedFace.value = null;
    highlight();
  } catch (reason) {
    console.error("模型加载失败", reason);
    error.value =
      "三维模型读取失败，请重新加载预览；仍失败时可下载上方 STEP 原件查看。";
  } finally {
    if (current === generation) loading.value = false;
  }
}

function pick(event: MouseEvent) {
  if (!mesh || !host.value) return;
  const rect = renderer.domElement.getBoundingClientRect();
  const position = new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1,
  );
  const ray = new THREE.Raycaster();
  ray.setFromCamera(position, camera);
  const hit = ray.intersectObject(mesh)[0];
  selectedFace.value = hit?.faceIndex != null ? faceIds[hit.faceIndex] : null;
  highlight();
}

onMounted(() => {
  if (!host.value) return;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    host.value.appendChild(renderer.domElement);
    scene = new THREE.Scene();
    scene.background = new THREE.Color("#edf1f4");
    camera = new THREE.PerspectiveCamera(40, 1, 0.1, 10000);
    camera.up.set(0, 0, 1);
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x516373, 2.7));
    const light = new THREE.DirectionalLight(0xffffff, 3);
    light.position.set(100, -200, 300);
    scene.add(light);
    observer = new ResizeObserver(() => {
      if (!host.value) return;
      const { clientWidth, clientHeight } = host.value;
      renderer.setSize(clientWidth, clientHeight);
      camera.aspect = clientWidth / Math.max(clientHeight, 1);
      camera.updateProjectionMatrix();
    });
    observer.observe(host.value);
    renderer.domElement.addEventListener("dblclick", pick);
    const draw = () => {
      animation = requestAnimationFrame(draw);
      controls.update();
      renderer.render(scene, camera);
    };
    draw();
    void load();
  } catch (reason) {
    console.error("三维预览初始化失败", reason);
    error.value = "当前设备暂时无法显示三维预览，可下载模型查看。";
  }
});
watch(() => props.url, load);
watch(() => props.highlightedFaces, highlight);
onBeforeUnmount(() => {
  generation++;
  cancelAnimationFrame(animation);
  observer?.disconnect();
  controls?.dispose();
  renderer?.dispose();
  mesh?.geometry.dispose();
  if (mesh) (mesh.material as THREE.Material).dispose();
});
</script>

<template>
  <div class="model-wrapper" v-loading="loading">
    <div ref="host" class="model-canvas" />
    <span class="model-hint"
      >拖动旋转 · 滚轮缩放 · 双击选面
      <b v-if="selectedFace"> / 面 {{ selectedFace }}</b></span
    ><el-alert v-if="error" :title="error" type="error" :closable="false">
      <el-button v-if="scene" size="small" :loading="loading" @click="load">
        重新加载预览
      </el-button>
    </el-alert>
  </div>
</template>
