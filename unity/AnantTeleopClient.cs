// ANANT XR teleoperation client for Meta Quest 3 (Unity + Meta XR SDK).
//
// REFERENCE IMPLEMENTATION: attach to an empty GameObject in a scene that has an OVRCameraRig
// with hand tracking enabled (OVRHand + OVRSkeleton on both hands). Tested against the
// message format of anant/xr/server.py; adjust bone names if your SDK version differs.
//
// Safety: the robot only moves while the LEFT-hand MIDDLE-finger pinch (deadman) is held.
// Release it, or lose tracking, and the arms hold their position.
//
// Coordinates are sent in a yaw-aligned body frame centred on the head:
// x right, y up, z forward (metres). Press the Start/Menu button to recentre.
using System;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using UnityEngine;

public class AnantTeleopClient : MonoBehaviour
{
    public string serverUrl = "ws://192.168.1.50:8765";   // Jetson IP
    public Transform head;                                 // OVRCameraRig/TrackingSpace/CenterEyeAnchor
    public OVRSkeleton leftSkeleton, rightSkeleton;
    public OVRHand leftHand, rightHand;
    public float sendHz = 30f;

    [Serializable] class HandMsg { public bool tracked; public float[] p = new float[3]; public float[] q = new float[4]; public float[] curls = new float[5]; }
    [Serializable] class FrameMsg { public double t; public bool enable; public float[] head = new float[3]; public HandMsg left = new HandMsg(), right = new HandMsg(); }

    ClientWebSocket ws;
    float nextSend;
    float yawRef;
    Vector3 headRefEuler;
    bool sending;

    async void Start()
    {
        ws = new ClientWebSocket();
        try { await ws.ConnectAsync(new Uri(serverUrl), CancellationToken.None); Debug.Log("ANANT connected"); }
        catch (Exception e) { Debug.LogError("ANANT connect failed: " + e.Message); }
        Recenter();
    }

    void Recenter() { yawRef = head.eulerAngles.y; headRefEuler = head.eulerAngles; }

    void Update()
    {
        if (OVRInput.GetDown(OVRInput.Button.Start)) Recenter();
        if (ws == null || ws.State != WebSocketState.Open || sending || Time.time < nextSend) return;
        nextSend = Time.time + 1f / sendHz;

        var msg = new FrameMsg
        {
            t = Time.timeAsDouble,
            enable = leftHand != null && leftHand.IsTracked && leftHand.GetFingerIsPinching(OVRHand.HandFinger.Middle),
        };
        msg.head = new[] { -Mathf.DeltaAngle(headRefEuler.y, head.eulerAngles.y),
                           -Mathf.DeltaAngle(headRefEuler.x, head.eulerAngles.x),
                            Mathf.DeltaAngle(headRefEuler.z, head.eulerAngles.z) };
        Fill(msg.left, leftHand, leftSkeleton);
        Fill(msg.right, rightHand, rightSkeleton);
        Send(JsonUtility.ToJson(msg));
    }

    async void Send(string json)
    {
        sending = true;
        try { await ws.SendAsync(new ArraySegment<byte>(Encoding.UTF8.GetBytes(json)), WebSocketMessageType.Text, true, CancellationToken.None); }
        catch (Exception e) { Debug.LogWarning("send failed: " + e.Message); }
        sending = false;
    }

    void Fill(HandMsg m, OVRHand hand, OVRSkeleton sk)
    {
        m.tracked = hand != null && hand.IsTracked && hand.HandConfidence == OVRHand.TrackingConfidence.High;
        if (!m.tracked) return;
        Quaternion frame = Quaternion.Euler(0, yawRef, 0), inv = Quaternion.Inverse(frame);
        Transform wrist = Bone(sk, OVRSkeleton.BoneId.Hand_WristRoot);
        if (wrist == null) { m.tracked = false; return; }
        Vector3 p = inv * (wrist.position - head.position);
        Quaternion q = inv * wrist.rotation;
        m.p = new[] { p.x, p.y, p.z };
        m.q = new[] { q.x, q.y, q.z, q.w };
        m.curls = new[] {
            Curl(sk, OVRSkeleton.BoneId.Hand_Thumb1, OVRSkeleton.BoneId.Hand_Thumb2, OVRSkeleton.BoneId.Hand_Thumb3, OVRSkeleton.BoneId.Hand_ThumbTip, 90f),
            Curl(sk, OVRSkeleton.BoneId.Hand_Index1, OVRSkeleton.BoneId.Hand_Index2, OVRSkeleton.BoneId.Hand_Index3, OVRSkeleton.BoneId.Hand_IndexTip, 170f),
            Curl(sk, OVRSkeleton.BoneId.Hand_Middle1, OVRSkeleton.BoneId.Hand_Middle2, OVRSkeleton.BoneId.Hand_Middle3, OVRSkeleton.BoneId.Hand_MiddleTip, 170f),
            Curl(sk, OVRSkeleton.BoneId.Hand_Ring1, OVRSkeleton.BoneId.Hand_Ring2, OVRSkeleton.BoneId.Hand_Ring3, OVRSkeleton.BoneId.Hand_RingTip, 170f),
            Curl(sk, OVRSkeleton.BoneId.Hand_Pinky2, OVRSkeleton.BoneId.Hand_Pinky3, OVRSkeleton.BoneId.Hand_PinkyTip, OVRSkeleton.BoneId.Hand_PinkyTip, 120f),
        };
    }

    static Transform Bone(OVRSkeleton sk, OVRSkeleton.BoneId id)
    {
        if (sk == null || sk.Bones == null) return null;
        foreach (var b in sk.Bones) if (b.Id == id) return b.Transform;
        return null;
    }

    // Sum of joint flexion along a finger, normalised by the typical full-fist angle.
    static float Curl(OVRSkeleton sk, OVRSkeleton.BoneId a, OVRSkeleton.BoneId b, OVRSkeleton.BoneId c, OVRSkeleton.BoneId d, float fullFist)
    {
        Transform A = Bone(sk, a), B = Bone(sk, b), C = Bone(sk, c), D = Bone(sk, d);
        if (A == null || B == null || C == null || D == null) return 0f;
        float total = Vector3.Angle(B.position - A.position, C.position - B.position)
                    + Vector3.Angle(C.position - B.position, D.position - C.position);
        return Mathf.Clamp01(total / fullFist);
    }

    void OnDestroy() { ws?.Dispose(); }
}
