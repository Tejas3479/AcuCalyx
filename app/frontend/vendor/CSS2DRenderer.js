/**
 * Three.js r128 CSS2DRenderer
 * Copyright 2010-2021 Three.js Authors
 * SPDX-License-Identifier: MIT
 */
(function () {
    class CSS2DObject extends THREE.Object3D {
        constructor(element = document.createElement('div')) {
            super();
            this.element = element;
            this.element.style.position = 'absolute';
            this.element.style.userSelect = 'none';
            this.element.setAttribute('draggable', false);
            this.addEventListener('removed', function () {
                this.traverse(function (object) {
                    if (object.element && object.element.parentNode !== null) {
                        object.element.parentNode.removeChild(object.element);
                    }
                });
            });
        }
        copy(source, recursive) {
            super.copy(source, recursive);
            this.element = source.element.cloneNode(true);
            return this;
        }
    }

    class CSS2DRenderer {
        constructor(parameters = {}) {
            let _width, _height;
            let _widthHalf, _heightHalf;
            const vector = new THREE.Vector3();
            const viewMatrix = new THREE.Matrix4();
            const viewProjectionMatrix = new THREE.Matrix4();
            const domElement = parameters.element !== undefined ? parameters.element : document.createElement('div');
            domElement.style.overflow = 'hidden';
            domElement.style.pointerEvents = 'none';
            this.domElement = domElement;

            this.getSize = function () {
                return { width: _width, height: _height };
            };

            this.render = function (scene, camera) {
                if (scene.matrixWorldAutoUpdate === true) scene.updateMatrixWorld();
                if (camera.parent === null && camera.matrixWorldAutoUpdate === true) camera.updateMatrixWorld();
                viewMatrix.copy(camera.matrixWorldInverse);
                viewProjectionMatrix.multiplyMatrices(camera.projectionMatrix, viewMatrix);
                renderObject(scene, scene, camera);
            };

            this.setSize = function (width, height) {
                _width = width;
                _height = height;
                _widthHalf = _width / 2;
                _heightHalf = _height / 2;
                domElement.style.width = width + 'px';
                domElement.style.height = height + 'px';
            };

            function renderObject(object, scene, camera) {
                if (object instanceof CSS2DObject) {
                    vector.setFromMatrixPosition(object.matrixWorld);
                    vector.applyMatrix4(viewProjectionMatrix);
                    const visible = (object.visible === true) && (vector.z >= -1 && vector.z <= 1) &&
                        (vector.x >= -1.1 && vector.x <= 1.1) && (vector.y >= -1.1 && vector.y <= 1.1);
                    object.element.style.display = visible ? '' : 'none';
                    if (visible) {
                        object.element.style.transform = 'translate(-50%, -50%) translate(' + (vector.x * _widthHalf + _widthHalf) + 'px,' + (-vector.y * _heightHalf + _heightHalf) + 'px)';
                    }
                }
                for (let i = 0, l = object.children.length; i < l; i++) {
                    renderObject(object.children[i], scene, camera);
                }
            }
        }
    }

    THREE.CSS2DObject = CSS2DObject;
    THREE.CSS2DRenderer = CSS2DRenderer;
})();
